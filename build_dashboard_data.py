"""Build data/dashboard.json for the job-market dashboard on tommyaliff.com.

Same steps as the exploration notebook, in one place:
  load raw slices -> split postings / membership -> derive work arrangement
  -> map slices to comparable groups (local groups: Virginia only)
  -> per-group stats -> one JSON file the page reads.
Usage: python3 build_dashboard_data.py
"""
import json, pathlib, re, statistics
import numpy as np
import pandas as pd
from analyze_snapshot import SKILLS, years

HERE = pathlib.Path(__file__).resolve().parent
RAW, OUT = HERE / "data" / "raw", HERE / "data" / "dashboard.json"

GROUPS = {  # slice -> dashboard group (us_entry_de / us_remote_de are skewed samples: left out)
    "local_de_towns": "Local data engineering",
    "local_de_metros": "Local data engineering",
    "local_adjacent": "Local related tech roles",
    "virginia_de": "Virginia data engineering",
    "us_all_de": "US data engineering",
}
ORDER = list(dict.fromkeys(GROUPS.values()))
ARRANGEMENTS = ["remote", "hybrid", "on-site", "unknown"]


def tidy_location(loc):
    """Display form 'City, VA': boards write 'Charlottesville, Virginia, United States' or 'Roanoke, VA 24011'."""
    if not isinstance(loc, str):
        return ""
    loc = re.sub(r",?\s*(United States|USA|US)\s*$", "", loc.strip(), flags=re.I)
    loc = re.sub(r"\bVirginia\b", "VA", loc)
    loc = re.sub(r"\s+\d{5}(-\d{4})?\s*$", "", loc)           # trailing ZIP
    return re.sub(r"\s*,\s*", ", ", loc).strip(" ,")


def load():
    frames = []
    for f in sorted(RAW.glob("*.json")):
        part = pd.DataFrame(json.loads(f.read_text()))
        part["slice"] = f.stem
        frames.append(part)
    all_jobs = pd.concat(frames, ignore_index=True)
    membership = all_jobs[["id", "slice"]].drop_duplicates()          # bridge table
    postings = all_jobs.drop(columns="slice").drop_duplicates(subset="id")
    return postings, membership


def derive(postings):
    text = postings["description"].fillna("").str.lower()
    src = postings["work_arrangement"].str.lower()
    conditions = [
        src.notna(),
        text.str.contains(r"fully remote|100% remote|remote position|this (?:role|position) is remote"),
        text.str.contains(r"\bhybrid\b|days? (?:a|per) week in (?:the )?office"),
        text.str.contains(r"on-?site|in[- ]office|in the office"),
    ]
    arr = np.select(conditions, [src, "remote", "hybrid", "on-site"], default="unknown")
    postings["arrangement"] = pd.Series(arr, index=postings.index).replace({"onsite": "on-site"})
    loc = postings["short_location"].fillna(postings["location"]).fillna("")
    postings["in_va"] = loc.str.contains(r",\s*(?:VA|Virginia)\b") | loc.str.strip().eq("Charlottesville")
    postings["text"] = (postings["job_title"].fillna("") + "\n" + postings["description"].fillna("")).str.lower()
    postings["salary"] = postings["avg_annual_salary_usd"].fillna(postings["estimated_avg_annual_salary_usd"])
    postings["min_years"] = postings["text"].map(years)
    return postings


def grouped(postings, membership):
    g = membership.assign(group=membership["slice"].map(GROUPS)).dropna(subset=["group"])
    g = g.merge(postings, on="id")
    g = g[~g["group"].str.startswith("Local") | g["in_va"]]   # local groups: Virginia only
    return g.drop_duplicates(subset=["id", "group"])             # towns + metros overlap


def bucket(y):
    return "0-1" if y <= 1 else "2-3" if y <= 3 else "4-5" if y <= 5 else "6+"


def group_stats(d):
    n = len(d)
    arr = d["arrangement"].value_counts()
    stated = n - arr.get("unknown", 0)
    ys = d["min_years"].dropna()
    sal = d["salary"].dropna()
    skills = {k: int(d["text"].str.contains(rx).sum()) for k, rx in SKILLS.items()}
    return {
        "n": n,
        "arrangement": {a: int(arr.get(a, 0)) for a in ARRANGEMENTS},
        "arrangement_of_stated": {a: round(float(arr.get(a, 0) / stated), 3) if stated else None
                                  for a in ARRANGEMENTS[:3]},
        "median_salary": int(statistics.median(sal)) if len(sal) else None,
        "salary_n": int(len(sal)),
        "years": {b: int((ys.map(bucket) == b).sum()) for b in ["0-1", "2-3", "4-5", "6+"]},
        "years_n": int(len(ys)),
        "median_years": float(statistics.median(ys)) if len(ys) else None,
        "skills": dict(sorted(((k, v) for k, v in skills.items() if v), key=lambda kv: -kv[1])),
    }


def main():
    postings, membership = load()
    postings = derive(postings)
    g = grouped(postings, membership)

    entry = postings[postings["seniority"].eq("entry_level")]["min_years"].dropna()
    local = g[g["group"].str.startswith("Local")].drop_duplicates(subset="id")
    local = local.sort_values("date_posted", ascending=False)
    # Reposts: the same company and title a few days apart, sometimes with a casing or
    # punctuation difference ("DAn Solutions" vs "Dan Solutions"). Keep the newest.
    norm = lambda s: s.fillna("").str.lower().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    local = local.assign(_k=norm(local["company"]) + "|" + norm(local["job_title"]))
    local = local.drop_duplicates(subset="_k").head(12)
    # Public fields only: no recruiter names/emails or other personal data leave this script.
    latest = [{"posted": str(r.date_posted)[:10], "title": r.job_title, "company": r.company,
               "location": tidy_location(r.short_location or r.location), "url": r.url,
               "group": r.group, "arrangement": r.arrangement} for r in local.itertuples()]

    out = {
        "generated": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "source": "JobsPipe (full descriptions), postings from the last 90 days",
        "total_postings": int(g["id"].nunique()),   # postings in the groups shown, not every pull
        "total_pulled": int(postings["id"].nunique()),
        "groups": {name: group_stats(g[g["group"] == name]) for name in ORDER},
        "entry_level": {"n": int(len(entry)),
                        "median_years": float(statistics.median(entry)) if len(entry) else None,
                        "share_0_1": round(float((entry <= 1).mean()), 3) if len(entry) else None},
        "latest_local": latest,
    }
    OUT.write_text(json.dumps(out, indent=2))
    for name in ORDER:
        s = out["groups"][name]
        print(f"{name:28s} n={s['n']:4d}  stated={s['arrangement_of_stated']}  "
              f"median ${s['median_salary']}  yrs {s['median_years']}")
    print("entry level:", out["entry_level"], "\nwrote", OUT)


if __name__ == "__main__":
    main()
