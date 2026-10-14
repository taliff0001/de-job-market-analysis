"""Summarize the JobsPipe snapshot: skills, certs, degree language, experience, seniority.
Usage: python3 analyze_snapshot.py  > snapshot_report.md
Stdlib only, so it runs anywhere."""
import json, pathlib, re, statistics, collections

RAW = pathlib.Path(__file__).resolve().parent / "data" / "raw"

SKILLS = {
 "SQL": r"\bsql\b", "Python": r"\bpython\b", "Java": r"\bjava\b(?!script)", "Scala": r"\bscala\b",
 "Spark": r"\bspark\b|pyspark", "Airflow": r"\bairflow\b", "dbt": r"\bdbt\b", "Kafka": r"\bkafka\b",
 "AWS": r"\baws\b|amazon web services", "Azure": r"\bazure\b", "GCP": r"\bgcp\b|google cloud|bigquery",
 "Snowflake": r"snowflake", "Databricks": r"databricks", "Redshift": r"redshift", "Glue": r"\baws glue\b|\bglue\b",
 "S3": r"\bs3\b", "Lambda": r"\blambda\b", "Terraform": r"terraform", "Docker": r"\bdocker\b",
 "Kubernetes": r"kubernetes|\bk8s\b", "Git": r"\bgit\b|github|gitlab", "CI/CD": r"ci/cd|\bcicd\b|continuous integration",
 "PostgreSQL": r"postgres", "Oracle": r"\boracle\b", "SQL Server": r"sql server|t-sql|\bssis\b",
 "NoSQL": r"nosql|mongodb|dynamodb|cassandra", "Data modeling": r"data model|dimensional model|star schema|kimball",
 "ETL/ELT": r"\betl\b|\belt\b", "Data warehouse": r"data warehous", "Data lake/lakehouse": r"data lake|lakehouse",
 "Power BI/Tableau": r"power ?bi|tableau|looker", "Linux": r"\blinux\b|\bunix\b|bash|shell script",
 "REST APIs": r"\brest\b|\bapis?\b", "Streaming": r"streaming|real-time|kinesis|flink",
 "Machine learning": r"machine learning|\bml\b", "GenAI/LLM": r"\bllm|generative ai|genai|large language",
 "Palantir": r"palantir|foundry", "Informatica": r"informatica",
}
CERTS = {
 "AWS DEA (Data Engineer Assoc)": r"data engineer[- ]associate|dea-c01",
 "AWS (any cert)": r"aws certifi|aws certified",
 "Azure DP-203/DP-700": r"dp-203|dp-700|azure data engineer associate|fabric data engineer",
 "GCP Prof. Data Engineer": r"professional data engineer",
 "Databricks cert": r"databricks certified|databricks certification",
 "Snowflake SnowPro": r"snowpro",
 "Security+ / DoD 8570": r"security\+|8570|8140",
 "Any 'certification' word": r"certif",
}
DEGREE = [
 ("Degree OR equivalent experience", r"(degree|bachelor'?s?)[^.]{0,80}(or equivalent|or comparable|equivalent experience|in lieu)|(equivalent (work )?experience|in lieu of)[^.]{0,80}degree"),
 ("Master's required/preferred", r"master'?s"),
 ("Bachelor's mentioned", r"bachelor'?s|\bb\.?s\.?\b in|\bbs\b in|undergraduate degree|4-year degree|degree in (computer|engineering|information|math|statistics)"),
]
CLEAR = r"clearance|ts/sci|top secret|\bsecret\b|public trust"

def load():
    out = {}
    for f in sorted(RAW.glob("*.json")):
        jobs = {j["id"]: j for j in json.loads(f.read_text())}
        out[f.stem] = list(jobs.values())
    return out

def pct(n, d): return f"{100*n/d:.0f}%" if d else "-"

def years(text):
    hits = [int(m.group(1)) for m in re.finditer(r"(\d{1,2})\+?\s*(?:-|to)?\s*\d{0,2}\s*\+?\s*years?", text) if int(m.group(1)) <= 15]
    return min(hits) if hits else None

def text_of(j): return ((j.get("job_title") or "") + "\n" + (j.get("description") or "")).lower()

def summarize(name, jobs):
    n = len(jobs); T = [text_of(j) for j in jobs]
    print(f"\n## {name}  (n={n})\n")
    sen = collections.Counter(j.get("seniority") or "unlabeled" for j in jobs)
    print("**Seniority:** " + ", ".join(f"{k} {v}" for k, v in sen.most_common()))
    rem = sum(1 for j in jobs if j.get("remote")); print(f"**Remote:** {pct(rem,n)}  ")
    sal = [j.get("avg_annual_salary_usd") or j.get("estimated_avg_annual_salary_usd") for j in jobs]
    sal = [s for s in sal if s]
    if sal: print(f"**Median salary (stated or estimated):** ${statistics.median(sal):,.0f} (n={len(sal)})  ")
    ys = [y for y in (years(t) for t in T) if y is not None]
    if ys:
        b = collections.Counter("0-1" if y <= 1 else "2-3" if y <= 3 else "4-5" if y <= 5 else "6+" for y in ys)
        print(f"**Min years asked (n={len(ys)} that state it):** " + ", ".join(f"{k}: {b[k]}" for k in ("0-1","2-3","4-5","6+")) + f"; median {statistics.median(ys):.0f}  ")
    print(f"**Clearance mentioned:** {pct(sum(bool(re.search(CLEAR,t)) for t in T), n)}  ")
    deg = {lab: sum(bool(re.search(rx, t)) for t in T) for lab, rx in DEGREE}
    nodeg = sum(1 for t in T if not re.search(r"degree|bachelor|master'?s", t))
    print("**Degree:** " + "; ".join(f"{k} {pct(v,n)}" for k, v in deg.items()) + f"; no degree mentioned at all {pct(nodeg,n)}  ")
    apps = [j.get("applicant_count") for j in jobs if j.get("applicant_count")]
    if apps: print(f"**Median applicants (where shown, n={len(apps)}):** {statistics.median(apps):.0f}  ")
    print("\n| Skill | Share |\n|---|---|")
    sk = sorted(((k, sum(bool(re.search(rx, t)) for t in T)) for k, rx in SKILLS.items()), key=lambda x: -x[1])
    for k, v in sk:
        if v: print(f"| {k} | {pct(v,n)} |")
    print("\n| Certification | Share |\n|---|---|")
    for k, rx in CERTS.items(): print(f"| {k} | {pct(sum(bool(re.search(rx,t)) for t in T), n)} |")
    comp = collections.Counter(j.get("company") for j in jobs)
    print("\n**Top employers:** " + ", ".join(f"{c} ({v})" for c, v in comp.most_common(8)))

def listing(name, jobs):
    print(f"\n### Every posting in {name}\n\n| Posted | Title | Company | Location | Level | Applicants |\n|---|---|---|---|---|---|")
    for j in sorted(jobs, key=lambda j: j.get("date_posted") or "", reverse=True):
        print(f"| {j.get('date_posted','')} | [{j.get('job_title','').replace('|','/')}]({j.get('url','')}) | {j.get('company','')} | {j.get('short_location') or j.get('location','')} | {j.get('seniority') or '-'} | {j.get('applicant_count') or '-'} |")

if __name__ == "__main__":
    data = load()
    allj = {j["id"]: j for js in data.values() for j in js}
    print(f"# Job-market snapshot\n\nSource: JobsPipe, full descriptions. {len(allj)} distinct postings across {len(data)} slices.")
    for name, jobs in data.items(): summarize(name, jobs)
    local = {j["id"]: j for k in ("local_de_towns", "local_de_metros", "local_adjacent") for j in data.get(k, [])}
    listing("local (DE + adjacent, deduped)", list(local.values()))
