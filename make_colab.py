"""Generates colab.ipynb (run once after editing the cells below). Kept so the notebook stays reviewable as code."""
import json

def md(s): return {"cell_type": "markdown", "metadata": {}, "source": s.strip("\n").splitlines(keepends=True)}
def code(s): return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                     "source": s.strip("\n").splitlines(keepends=True)}

cells = [
md("""
# Explore the data engineering job market yourself

This notebook rebuilds the data behind [tommyaliff.com/job-market](https://tommyaliff.com/job-market/) from fresh job postings, then lets you poke at it.

**What you need:** a free [JobsPipe](https://jobspipe.dev) API key. That's it.

**Steps:** run the cells top to bottom (Runtime → Run all works). The second cell asks for your key; it's typed into a hidden prompt and never saved in the notebook.

**Credits:** each posting pulled costs one JobsPipe credit (repeats in the same month are free). The default pull below is at most **450 postings**. Lower the numbers in the third cell to spend less.
"""),
code("""
# 1. Get the code (Colab starts empty; this is skipped if you're already in the repo)
import os, pathlib
if not pathlib.Path("build_dashboard_data.py").exists():
    !git clone -q https://github.com/taliff0001/de-job-market-analysis.git
    os.chdir("de-job-market-analysis")
print("Working in", os.getcwd())
"""),
code("""
# 2. Your JobsPipe API key (hidden prompt; not stored in the notebook)
from getpass import getpass
if not os.environ.get("JOBSPIPE_API_KEY"):
    os.environ["JOBSPIPE_API_KEY"] = getpass("JobsPipe API key: ")
print("Key set." if os.environ["JOBSPIPE_API_KEY"] else "No key entered.")
"""),
code("""
# 3. Pull postings. Slice name -> how many postings (credits) at most.
import pull_jobspipe as pj
PULL = {
    "local_de_towns": 50,      # data engineering titles, Roanoke-area towns (filtered to Virginia later)
    "local_de_metros": 25,     # data engineering titles, Roanoke/Lynchburg/Blacksburg/Charlottesville metros
    "local_adjacent": 75,      # software, analyst, data science, BI, database titles in those metros
    "virginia_de": 150,        # data engineering titles statewide
    "us_all_de": 150,          # same titles nationwide (the fair comparison for Virginia)
}
REFRESH = False                # True = pull again even if data/raw already has the files

for name, cap in PULL.items():
    filters, _ = pj.SLICES[name]
    pj.SLICES[name] = (filters, cap)
todo = [n for n in PULL if REFRESH or not (pj.OUT / f"{n}.json").exists()]
if todo:
    import sys
    sys.argv = ["pull_jobspipe.py", *todo]
    pj.main()
else:
    print("Already pulled; set REFRESH = True to pull again.")
"""),
md("""
## The cleaned data

`build_dashboard_data.py` does the cleaning described in the [README](https://github.com/taliff0001/de-job-market-analysis#decisions-worth-knowing-about): one row per posting, a posting↔slice bridge table, work arrangement from the source field or the description, and local groups filtered to Virginia.
"""),
code("""
import pandas as pd
import build_dashboard_data as b

postings, membership = b.load()
postings = b.derive(postings)
g = b.grouped(postings, membership)        # one row per posting per dashboard group
print(len(postings), "distinct postings pulled;", g["id"].nunique(), "in the comparison groups")
g["group"].value_counts()
"""),
md("## Where the work happens\nShare of each group's postings. `normalize=\"index\"` makes each row add up to 1."),
code("""
pd.crosstab(g["group"], g["arrangement"], normalize="index").round(2)
"""),
code("""
# Same thing, counting only postings that state an arrangement
known = g[g["arrangement"] != "unknown"]
pd.crosstab(known["group"], known["arrangement"], normalize="index").round(2)
"""),
md("## Pay and experience asked"),
code("""
g.groupby("group").agg(postings=("id", "size"),
                       median_salary=("salary", "median"),
                       median_years_asked=("min_years", "median")).round(0)
"""),
md("## Skills named in postings\nShare of each group's postings that mention the skill (regular expressions in `analyze_snapshot.py`)."),
code("""
from analyze_snapshot import SKILLS
skills = pd.DataFrame({k: g["text"].str.contains(rx) for k, rx in SKILLS.items()})
skills["group"] = g["group"].values
share = skills.groupby("group").mean().T.round(2)
share.sort_values("US data engineering", ascending=False).head(15)
"""),
code("""
share.sort_values("US data engineering", ascending=False).head(12).plot.barh(figsize=(8, 7)).invert_yaxis()
"""),
md("""
## Your turn

Some questions to try:

- Which employers post the most in Virginia? `g[g.group == "Virginia data engineering"]["company"].value_counts().head(10)`
- How many postings mention a security clearance? Try `g["text"].str.contains("clearance")` by group.
- Change a title list in `pull_jobspipe.py` (say, add `"etl"`), set `REFRESH = True`, and see what moves.

`python build_dashboard_data.py` writes `data/dashboard.json`, the exact file the live dashboard reads.
"""),
]

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
      "language_info": {"name": "python"}, "colab": {"provenance": []}}, "nbformat": 4, "nbformat_minor": 5}
json.dump(nb, open("colab.ipynb", "w"), indent=1)
print("wrote colab.ipynb with", len(cells), "cells")
