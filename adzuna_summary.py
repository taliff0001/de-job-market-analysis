"""
Summarize the Adzuna pulls and build the data for the Virginia map.

Usage:  .venv/bin/python adzuna_summary.py
Outputs:
  data/adzuna_ads.csv        every kept ad, one row each, with group/category/distance
  data/va_map_cities.csv     one row per Virginia city: DE count, adjacent count, lat/lon

Rules (all CHECKED against real responses on 10/17):
- title_only matches all words in any order, so every title is re-checked with a regex.
- "Local" = real distance <= 100 miles from downtown Roanoke, computed from each ad's
  latitude/longitude (Adzuna's radius is loose and its `distance` acts as miles).
- Ads located only as "Virginia, US" carry the state's centre point as coordinates:
  they're counted, but never mapped and never called local.
- An ad is DE if its title contains "data engineer(ing)"; DE always wins over adjacent,
  and each ad id is kept once.
"""
import json, pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).parent
RAW = ROOT / "data" / "raw"
ROANOKE = (37.2710, -79.9414)                  # downtown Roanoke (ZIP 24011)

ADJ_PATTERNS = {                               # what each adjacent pull must really contain
    "analytics_engineer":    r"analytics engineer",
    "etl":                   r"\betl\b",
    "data_analyst":          r"data analyst",
    "business_intelligence": r"business intelligence|\bbi (?:developer|engineer|analyst)\b",
    "database":              r"database|\bdba\b",
    "data_scientist":        r"data scientist",
}


def miles_from_roanoke(lat, lon):
    """Great-circle (haversine) distance in miles; works on whole columns at once."""
    lat0, lon0 = np.radians(ROANOKE[0]), np.radians(ROANOKE[1])
    lat, lon = np.radians(lat), np.radians(lon)
    a = np.sin((lat - lat0) / 2) ** 2 + np.cos(lat0) * np.cos(lat) * np.sin((lon - lon0) / 2) ** 2
    return 3958.8 * 2 * np.arcsin(np.sqrt(a))   # 3958.8 = Earth's radius in miles


# 1. Load every raw file into one DataFrame
frames = []
for f in sorted(RAW.glob("adzuna_*.json")):
    blob = json.loads(f.read_text())
    df = pd.json_normalize(blob["results"])            # nested JSON -> columns like "location.area"
    group, _, category = blob["group"].partition("__")  # va_adjacent__etl -> ("va_adjacent", "etl")
    df["group"], df["category"] = group, category or "data_engineer"
    df["adzuna_count"] = blob["count"]                  # Adzuna's total matches for that query
    frames.append(df)
ads = pd.concat(frames, ignore_index=True)
ads["id"] = ads["id"].astype(str)

# 2. Clean titles and locations
ads["title"] = ads["title"].str.replace(r"<[^>]+>", "", regex=True)      # strip <strong> highlight tags
ads["state"] = ads["location.area"].str[1]                              # ["US","Virginia",...] -> "Virginia"
ads["city_known"] = ads["location.area"].str.len() > 2                  # False = only "Virginia, US"
ads["miles"] = miles_from_roanoke(ads["latitude"], ads["longitude"]).round(1)
ads.loc[~ads["city_known"], "miles"] = np.nan                           # state-centre points aren't real places

# 3. Decide what each ad really is
is_de = ads["title"].str.contains(r"data engineer", case=False, na=False)   # also matches "engineering"
ads.loc[is_de, "category"] = "data_engineer"
adj_ok = pd.Series(False, index=ads.index)
for cat, pat in ADJ_PATTERNS.items():
    rows = ads["category"] == cat
    adj_ok |= rows & ads["title"].str.contains(pat, case=False, regex=True, na=False)
ads = ads[is_de | adj_ok]                                   # drops "Data Center Engineer" and other noise
ads["kind"] = np.where(ads["category"] == "data_engineer", "DE", "adjacent")

# one row per ad: DE rows first, so an ad found by both a DE and an adjacent pull stays DE
ads = (ads.sort_values("kind", key=lambda s: s.ne("DE"))
          .drop_duplicates(subset=["group", "id"]))
va = ads[ads["group"].isin(["virginia_de", "va_adjacent", "local_de"]) & ads["state"].eq("Virginia")]
va = va.drop_duplicates(subset="id")                        # local_de and virginia_de overlap

# 4. Report
print("Adzuna total matches per query (90 days, before title checks):")
print(ads.groupby(["group", "category"])["adzuna_count"].first().to_string(), "\n")

print("Virginia ads kept, by kind (after title checks, one row per ad):")
print(va["kind"].value_counts().to_string())
print("  of which location is only 'Virginia, US' (not mappable):", int((~va["city_known"]).sum()), "\n")

print("Distance from Roanoke, Virginia ads with a real city:")
bands = pd.cut(va["miles"], [0, 60, 100, 150, 1000], labels=["<=60 mi", "60-100", "100-150", "150+"])
print(pd.crosstab(bands, va["kind"]).to_string(), "\n")

print("Top Virginia cities:")
print(pd.crosstab(va["location.display_name"], va["kind"]).assign(total=lambda t: t.sum(axis=1))
        .sort_values("total", ascending=False).head(12).to_string(), "\n")

us = ads[(ads["group"] == "us_de") & (ads["kind"] == "DE")]
print(f"US DE sample: {us['id'].nunique()} unique ads, {us['created'].min()[:10]} to {us['created'].max()[:10]}")
win = va[(va["kind"] == "DE") & (va["created"] >= us["created"].min())]
print(f"Virginia DE ads in that same window: {win['id'].nunique()}")

# 5. Outputs
ads.to_csv(ROOT / "data" / "adzuna_ads.csv", index=False)
cities = (va[va["city_known"]]
          .groupby("location.display_name")
          .agg(lat=("latitude", "mean"), lon=("longitude", "mean"),
               de=("kind", lambda k: (k == "DE").sum()),
               adjacent=("kind", lambda k: (k == "adjacent").sum()),
               miles=("miles", "mean"))
          .round({"lat": 4, "lon": 4, "miles": 0})
          .sort_values("de", ascending=False))
cities.to_csv(ROOT / "data" / "va_map_cities.csv")
print(f"\nwrote data/adzuna_ads.csv and data/va_map_cities.csv ({len(cities)} cities)")
