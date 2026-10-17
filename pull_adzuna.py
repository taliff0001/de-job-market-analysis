"""
Pull job ads from the Adzuna API into data/raw/adzuna_*.json (one file per group).

Usage:  .venv/bin/python pull_adzuna.py
Reads ADZUNA_APP_ID / ADZUNA_APP_KEY from the repo's .env (same pattern as pull_jobspipe.py).
Free tier: 25 calls/minute, 250/day. This run uses about 63 calls (~3 minutes).

What Adzuna is used for (decided 10/17): counts, titles, employers, geography.
NOT salary: almost every Adzuna DE salary is Adzuna's own estimate (salary_is_predicted=1).
"""
import json, math, os, pathlib, time
import requests

ROOT = pathlib.Path(__file__).parent           # the repo folder (where this file lives)
RAW = ROOT / "data" / "raw"                    # raw responses land here (already gitignored)
BASE = "https://api.adzuna.com/v1/api/jobs/us/search/{page}"   # US endpoint; pages start at 1
PER_PAGE = 50        # results per page (50 is the most Adzuna returns)
DAYS = 90            # same 90-day window for every group, so groups are comparable
PAUSE = 2.6          # seconds between calls -> stays under 25 calls/minute
US_PAGES = 20        # US is huge: sample 20 pages (~1,000 ads) spread across the whole window


def load_keys():
    """Read the two Adzuna keys from the environment or .env (no python-dotenv needed)."""
    keys = {k: os.environ.get(k) for k in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")}
    env = ROOT / ".env"
    for line in (env.read_text().splitlines() if env.exists() else []):
        name, _, value = line.partition("=")              # split "NAME=value" at the first '='
        name = name.strip()
        if name in keys and not keys[name]:
            keys[name] = value.strip().strip('"').strip("'")
    if not all(keys.values()):
        raise SystemExit("ADZUNA_APP_ID / ADZUNA_APP_KEY missing from .env")
    return keys["ADZUNA_APP_ID"], keys["ADZUNA_APP_KEY"]


APP_ID, APP_KEY = load_keys()


def get_page(page, params):
    """Fetch one page of results and return the parsed JSON (a dict)."""
    query = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "results_per_page": PER_PAGE,
        "max_days_old": DAYS,
        "sort_by": "date",               # newest first, so page N is a slice of the time window
        "salary_include_unknown": 1,     # keep ads with no salary (needed for honest counts)
        "content-type": "application/json",
        **params,                        # the group's own filters (title words, location)
    }
    r = requests.get(BASE.format(page=page), params=query, timeout=30)
    r.raise_for_status()                 # stop loudly on a bad key, rate limit, etc.
    time.sleep(PAUSE)
    return r.json()


def pull(name, params, max_pages=None):
    """Pull one group: every page if max_pages is None, else max_pages pages spread evenly."""
    first = get_page(1, params)
    total = first["count"]                               # Adzuna's total number of matches
    n_pages = max(1, math.ceil(total / PER_PAGE))
    if max_pages is None or n_pages <= max_pages:
        pages = list(range(1, n_pages + 1))
    else:
        # evenly spaced pages from 1 to the last page, so the sample spans all 90 days
        step = (n_pages - 1) / (max_pages - 1)
        pages = sorted({round(1 + i * step) for i in range(max_pages)})

    results = list(first["results"])
    seen = {r["id"] for r in results}
    for p in pages[1:]:                                  # page 1 is already fetched
        try:
            batch = get_page(p, params)["results"]
        except requests.HTTPError as e:                  # deep pages can be refused; skip, don't die
            print(f"  {name}: page {p} skipped ({e.response.status_code})")
            continue
        new = [r for r in batch if r["id"] not in seen]
        # CHECKED 10/17: past roughly page 100, Adzuna keeps returning the same page.
        # A page with nothing new means we've hit that wall: stop instead of wasting calls.
        if not new:
            print(f"  {name}: page {p} returned only repeats; stopping (Adzuna paging limit)")
            break
        seen.update(r["id"] for r in new)
        results += new

    out = {"group": name, "params": params, "count": total, "pages": pages, "results": results}
    (RAW / f"adzuna_{name}.json").write_text(json.dumps(out, indent=1))
    print(f"{name:14} {total:>6} matches | {len(pages):>3} pages | {len(results):>5} ads saved", flush=True)


# Radius around downtown Roanoke (ZIP 24011 can't be confused with Roanoke, Texas).
# CHECKED 10/17: for the US endpoint, `distance` behaves as MILES (distance=161 returned ads up
# to 160 mi away, incl. Richmond), even though the docs say kilometres. The radius is also loose,
# so the summary recomputes real distance from each ad's latitude/longitude and filters on that.
LOCAL = {"where": "24011", "distance": 161}

GROUPS = [
    # (file name,     filters,                                                                 max_pages)
    ("local_de",      {"title_only": "data engineer", **LOCAL},                                None),
    # Statewide, using Adzuna's structured location fields instead of a text search
    ("virginia_de",   {"title_only": "data engineer", "location0": "US", "location1": "Virginia"}, 40),
    # National sample: 20 pages spread across the 90 days
    ("us_de",         {"title_only": "data engineer"},                                         US_PAGES),
    # Local related titles (software engineer alone is ~31 pages): add back later, capped.
]

if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    for name, params, max_pages in GROUPS:
        pull(name, params, max_pages)
