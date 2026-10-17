"""
Pull Virginia job ads for titles ADJACENT to data engineering (for the two-colour map).

Usage:  .venv/bin/python pull_adzuna_adjacent.py
Writes data/raw/adzuna_va_adjacent__<title>.json. Uses ~39 calls.

CHECKED 10/17 before writing this:
- title_only matches ALL the words in ANY order, not the exact phrase
  ("data engineer" also matched "Data Center Engineer"), so adzuna_summary.py
  re-checks every title with a regex.
- Some adjacent ads are data engineering ads we already have (analytics engineer: 18 of 50
  on page 1; ETL: 14 of 46). The summary drops any id already in the DE file, and any
  title containing "data engineer" goes to the DE colour, never to "adjacent".
- Location fields location0/location1 return Virginia only (one DC ad slipped into
  data scientist; the summary keeps state == "Virginia").
- Software engineer is left out on purpose (10x the volume; it would bury the DE dots).
"""
from pull_adzuna import pull

VA = {"location0": "US", "location1": "Virginia"}

ADJACENT = [
    ("va_adjacent__analytics_engineer",    "analytics engineer"),     # ~106 matches, 3 pages
    ("va_adjacent__etl",                   "etl"),                    # ~46, 1 page
    ("va_adjacent__data_analyst",          "data analyst"),           # ~505, 11 pages
    ("va_adjacent__business_intelligence", "business intelligence"),  # ~94, 2 pages
    ("va_adjacent__database",              "database"),               # ~337, 7 pages
    ("va_adjacent__data_scientist",        "data scientist"),         # ~720, 15 pages
]

if __name__ == "__main__":
    for name, words in ADJACENT:
        pull(name, {"title_only": words, **VA}, max_pages=20)
