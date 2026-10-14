"""One-time JobsPipe snapshot for Tutorial 02.

Pulls full job postings for several market slices and saves raw JSON per slice.
Credits: 1 per distinct job per calendar month (repeats in the same month are free).
Usage: python3 pull_jobspipe.py   (reads JOBSPIPE_API_KEY from the repo's .env)
"""
import json, pathlib, time, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent
OUT = pathlib.Path(__file__).resolve().parent / "data" / "raw"
API = "https://api.jobspipe.dev/v1/jobs/search"

DE = ["data engineer", "analytics engineer", "data platform", "etl developer",
      "data integration", "data warehouse", "data architect"]
ADJ = ["data analyst", "database", "sql developer", "bi developer", "business intelligence",
       "python developer", "software engineer", "software developer", "reporting analyst",
       "data scientist", "machine learning"]
METROS = ["40220", "31340", "13980", "16820"]  # Roanoke, Lynchburg, Blacksburg-Christiansburg, Charlottesville
TOWNS = ["Roanoke", "Salem, VA", "Lynchburg", "Blacksburg", "Christiansburg", "Radford",
         "Charlottesville", "Daleville"]

SLICES = {  # name: (filters, max jobs)
    "local_de_towns":   ({"job_title_or": DE, "job_location_or": TOWNS, "posted_at_max_age_days": 90}, 50),
    "local_de_metros":  ({"job_title_or": DE, "metro_code_or": METROS, "posted_at_max_age_days": 90}, 25),
    "local_adjacent":   ({"job_title_or": ADJ, "metro_code_or": METROS, "posted_at_max_age_days": 90}, 75),
    "us_entry_de":      ({"job_title_or": DE, "job_country_code_or": ["US"],
                          "job_seniority_or": ["entry", "internship", "associate"], "posted_at_max_age_days": 90}, 300),
    "us_remote_de":     ({"job_title_or": DE, "remote": True, "job_country_code_or": ["US"],
                          "posted_at_max_age_days": 30}, 300),
    "virginia_de":      ({"job_title_or": DE, "region_or": ["US-VA"], "posted_at_max_age_days": 90}, 150),
    # Same filters as virginia_de, nationwide: the fair US comparison (no seniority/remote filter).
    "us_all_de":        ({"job_title_or": DE, "job_country_code_or": ["US"], "posted_at_max_age_days": 90}, 150),
}

def load_key():
    import os
    if os.environ.get("JOBSPIPE_API_KEY"):          # e.g. set from the Colab notebook
        return os.environ["JOBSPIPE_API_KEY"].strip()
    env = ROOT / ".env"
    for line in (env.read_text().splitlines() if env.exists() else []):
        if line.startswith("JOBSPIPE_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("JOBSPIPE_API_KEY missing from .env")

def post(key, body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt); continue
            raise SystemExit(f"HTTP {e.code}: {e.read().decode()[:300]}")
    raise SystemExit("gave up after retries")

def main():
    import sys
    key = load_key(); OUT.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[1:] or list(SLICES)  # e.g. `python3 pull_jobspipe.py us_all_de` pulls just that slice
    for name in wanted:
        filters, cap = SLICES[name]
        jobs, cursor = [], None
        while len(jobs) < cap:
            body = dict(filters, limit=min(25, cap - len(jobs)))
            if cursor: body["cursor"] = cursor
            r = post(key, body); time.sleep(0.6)  # free tier: 2 req/s
            jobs += r.get("data", [])
            m = r.get("metadata", {}); cursor = m.get("next_cursor")
            if not cursor or not r.get("data"): break
        (OUT / f"{name}.json").write_text(json.dumps(jobs))
        print(f"{name:18s} {len(jobs):4d} jobs   credits remaining: {m.get('credits_remaining')}")

if __name__ == "__main__":
    main()
