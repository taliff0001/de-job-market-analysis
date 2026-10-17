"""
Build va_map.html: Virginia data engineering vs adjacent job postings, one bubble pair per county.

Usage:  .venv/bin/python build_va_map.py   (run adzuna_summary.py first; reads data/adzuna_ads.csv)
Output: va_map.html (self-contained preview; Leaflet + CARTO tiles from CDNs)

Design choices (10/17):
- County / independent-city level: Adzuna geocodes to neighbourhoods ("Tysons Corner",
  "Fort Myer"), which would draw ~100 overlapping dots in Northern Virginia.
- Bubble AREA is proportional to the count (radius ~ sqrt), the honest encoding for bubbles.
- Orange = data engineering (same orange as "Virginia" on the dashboard), blue = adjacent.
  Pair validated with the dataviz palette checker (colour-blind safe, light + dark).
- Ads located only as "Virginia, US" sit on the state's centre point: excluded from the map,
  reported in the footnote.
"""
import ast, json, pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).parent
ads = pd.read_csv(ROOT / "data" / "adzuna_ads.csv")

va = ads[ads["group"].isin(["virginia_de", "va_adjacent", "local_de"]) & ads["state"].eq("Virginia")]
va = va.drop_duplicates(subset="id")                      # one row per ad across the pulls
area = va["location.area"].apply(ast.literal_eval)       # CSV stored the list as text; turn it back into a list
va = va.assign(county=area.str[2])                        # ["US","Virginia","Fairfax County",...] -> "Fairfax County"
# CHECKED 10/17: Adzuna labels Richmond city "Richmond County" (a different, rural county on the
# Northern Neck). The coordinates are Richmond city's, so fix the label.
va.loc[va["county"].eq("Richmond County") & va["longitude"].gt(-77.6), "county"] = "Richmond (city)"
# CHECKED 10/17: 2 ads labeled "Halifax County" (on the NC line, ~36.8 N) carry coordinates in
# Tysons/Vienna, Fairfax County. Trust the coordinates.
va.loc[va["county"].eq("Halifax County") & va["latitude"].gt(38.5), "county"] = "Fairfax County"
unmapped = int(va["county"].isna().sum())                 # the "Virginia, US"-only ads
mapped = va[va["county"].notna()]

counties = (mapped.groupby("county")
            .agg(lat=("latitude", "mean"), lon=("longitude", "mean"),
                 de=("kind", lambda k: int((k == "DE").sum())),
                 adj=("kind", lambda k: int((k == "adjacent").sum())),
                 miles=("miles", "mean"))
            .reset_index())
counties["total"] = counties["de"] + counties["adj"]
counties = counties.sort_values("total", ascending=False)

de_total = int((va["kind"] == "DE").sum())
de_100 = int(((va["kind"] == "DE") & (va["miles"] <= 100)).sum())
de_60 = int(((va["kind"] == "DE") & (va["miles"] <= 60)).sum())
first, last = va["created"].min()[:10], va["created"].max()[:10]

payload = {
    "counties": counties[["county", "lat", "lon", "de", "adj", "miles"]].round(4).to_dict("records"),
    "roanoke": [37.2710, -79.9414],
}

html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Virginia DE Jobs Map</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/topojson-client@3/dist/topojson-client.min.js"></script>
<style>
  /* the map itself is always light (Tommy, 10/17); only the page around it follows light/dark */
  :root {{ --map-bg:#fcfcfb; --map-land:#dbe5d2; --map-line:#b7c4ab; --map-border:#5f6b55; --map-ring:#3d3d39;
          --map-ink:#1f1f1d; --map-de:#c2410c; --map-adj:#2f6fbf; }}
  :root {{ --bg:#fcfcfb; --ink:#1f1f1d; --ink2:#55544f; --muted:#7a7972; --rule:#dedcd5;
          --de:#c2410c; --adj:#2f6fbf; --ring:#55544f; --land:#f3f2ee; }}
  /* dark: follows the browser unless the toggle forces light; the toggle can also force dark */
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{ --bg:#1a1a19; --ink:#ecebe6; --ink2:#b9b8b1; --muted:#8f8e88; --rule:#3a3a37;
            --de:#d95926; --adj:#4a8ad6; --ring:#b9b8b1; --land:#232322; }} }}
  :root[data-theme="dark"] {{ --bg:#1a1a19; --ink:#ecebe6; --ink2:#b9b8b1; --muted:#8f8e88; --rule:#3a3a37;
            --de:#d95926; --adj:#4a8ad6; --ring:#b9b8b1; --land:#232322; }}
  .top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }}
  #theme {{ font:inherit; font-size:.85rem; color:var(--ink2); background:var(--bg); border:1px solid var(--rule);
           border-radius:6px; padding:4px 10px; cursor:pointer; white-space:nowrap; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
  main {{ max-width:1000px; margin:0 auto; padding:24px 16px 40px; }}
  h1 {{ font-size:1.45rem; line-height:1.25; margin:0 0 6px; }}
  .read {{ color:var(--ink2); margin:0 0 14px; }}
  .legend {{ display:flex; gap:18px; flex-wrap:wrap; font-size:.9rem; color:var(--ink2); margin-bottom:8px; }}
  .sw {{ display:inline-block; width:12px; height:12px; border-radius:50%; vertical-align:-1px; margin-right:6px; }}
  .ringsw {{ display:inline-block; width:14px; height:14px; border:1.5px dashed var(--ring); border-radius:50%; vertical-align:-3px; margin-right:6px; }}
  #map {{ height:560px; border:1px solid var(--rule); border-radius:8px; }}
  .leaflet-container {{ background:var(--map-bg); font:inherit; }}
  .leaflet-tooltip {{ background:var(--map-bg); color:var(--map-ink); border:1px solid var(--map-line); box-shadow:none; }}
  .rlabel {{ background:none; border:none; box-shadow:none; color:var(--map-ink); font-size:.8rem; font-weight:600; }}
  .rlabel::before {{ display:none; }}
  .note {{ font-size:.82rem; color:var(--muted); margin-top:10px; }}
  details {{ margin-top:14px; font-size:.9rem; }}
  table {{ border-collapse:collapse; margin-top:8px; }}
  th, td {{ text-align:right; padding:3px 10px; border-bottom:1px solid var(--rule); }}
  th:first-child, td:first-child {{ text-align:left; }}
</style></head>
<body><main>
<div class="top"><h1>Virginia's data engineering jobs are in Northern Virginia and Richmond, not near Roanoke</h1><button id="theme" type="button">Light / dark</button></div>
<p class="read">{de_total} data engineering postings in Virginia over 90 days ({first} to {last}).
  Within 100 miles of Roanoke: {de_100} on Adzuna, all in Charlottesville; a second source (JobsPipe) also found 3 in Blacksburg, about 40 miles away. None in Roanoke itself.</p>
<div class="legend">
  <span><span class="sw" style="background:var(--map-de)"></span>Data engineering (title says "data engineer")</span>
  <span><span class="sw" style="background:var(--map-adj)"></span>Adjacent roles (analyst, analytics engineer, ETL, BI, database, data scientist)</span>
  <span><span class="ringsw"></span>60 and 100 miles from Roanoke</span>
</div>
<div id="map" role="img" aria-label="Map of Virginia job postings by county; see the table below for the numbers."></div>
<p class="note">Bubble area = number of postings in that county or independent city. Source: Adzuna API, pulled Oct 17, 2026;
  every title re-checked by hand-written rules. {unmapped} postings listed only as "Virginia, US" have no real location and aren't mapped.
  A second source (JobsPipe) found 8 data engineering postings within 100 miles of Roanoke in the same window
  (5 Charlottesville, 3 Blacksburg).</p>
<details><summary>Table view</summary><table id="tbl"><thead><tr><th>County / city</th><th>Data engineering</th><th>Adjacent</th><th>Miles from Roanoke</th></tr></thead><tbody></tbody></table></details>
</main>
<script>
const DATA = {json.dumps(payload)};
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const dark = matchMedia('(prefers-color-scheme: dark)');
const map = L.map('map', {{ scrollWheelZoom:false, zoomSnap:0.25 }}).fitBounds([[36.54,-83.68],[39.47,-75.24]]);
// No tile service: CARTO now needs an API key (checked 10/17). Draw Virginia's own county lines instead
// (US Census boundaries packaged by us-atlas). Fewer pixels, follows light/dark, no key.
map.attributionControl.addAttribution('Boundaries: US Census Bureau via us-atlas');
const base = L.layerGroup().addTo(map);
let topo = null;
fetch('https://cdn.jsdelivr.net/npm/us-atlas@3/counties-10m.json').then(r => r.json()).then(t => {{ topo = t; drawBase(); }});
function drawBase() {{
  if (!topo) return;
  base.clearLayers();
  const va = g => String(g.id).startsWith('51');
  const counties = topojson.feature(topo, {{ type:'GeometryCollection', geometries: topo.objects.counties.geometries.filter(va) }});
  const state = topojson.feature(topo, {{ type:'GeometryCollection', geometries: topo.objects.states.geometries.filter(g => String(g.id) === '51') }});
  L.geoJSON(counties, {{ style: {{ color: css('--map-line'), weight: 0.8, fill: true, fillColor: css('--map-land'), fillOpacity: 1 }}, interactive:false }}).addTo(base);
  L.geoJSON(state, {{ style: {{ color: css('--map-border'), weight: 1.5, fill: false }}, interactive:false }}).addTo(base);
  base.eachLayer(l => l.bringToBack && l.bringToBack());
}}

const layer = L.layerGroup().addTo(map);
const maxN = Math.max(...DATA.counties.flatMap(c => [c.de, c.adj]));
const r = n => n ? Math.max(4, 34 * Math.sqrt(n / maxN)) : 0;   // area ~ count; 8px minimum diameter

function draw() {{
  layer.clearLayers();
  const R = DATA.roanoke;
  [60, 100].forEach(mi => L.circle(R, {{ radius: mi * 1609.34, color: css('--map-ring'), weight:1.5, dashArray:'5 5', fill:false, interactive:false }}).addTo(layer));
  L.circleMarker(R, {{ radius:4, color:css('--map-bg'), weight:2, fillColor:css('--map-ink'), fillOpacity:1 }})
    .bindTooltip('Roanoke', {{ permanent:true, direction:'right', className:'rlabel' }}).addTo(layer);
  // per county: draw the bigger bubble first so the smaller one stays visible on top
  DATA.counties.forEach(c => {{
    const tip = `<b>${{c.county}}</b><br>Data engineering: ${{c.de}}<br>Adjacent: ${{c.adj}}<br>${{Math.round(c.miles)}} mi from Roanoke`;
    [['adj', '--map-adj'], ['de', '--map-de']].map(([k, v]) => [c[k], v])
      .filter(([n]) => n > 0).sort((a, b) => b[0] - a[0])
      .forEach(([n, v]) => L.circleMarker([c.lat, c.lon], {{ radius:r(n), color:css('--map-bg'), weight:2,
        fillColor:css(v), fillOpacity:0.85 }}).bindTooltip(tip, {{ sticky:true }}).addTo(layer));
  }});
}}
draw();
dark.addEventListener('change', () => {{ drawBase(); draw(); }});
// toggle: flips between light and dark, remembered per visitor (try/catch: storage can be blocked)
const root = document.documentElement;
try {{ const saved = localStorage.getItem('va-map-theme'); if (saved) root.dataset.theme = saved; }} catch (e) {{}}
drawBase(); draw();
document.getElementById('theme').addEventListener('click', () => {{
  const isDark = root.dataset.theme ? root.dataset.theme === 'dark' : dark.matches;
  root.dataset.theme = isDark ? 'light' : 'dark';
  try {{ localStorage.setItem('va-map-theme', root.dataset.theme); }} catch (e) {{}}
  drawBase(); draw();
}});

document.querySelector('#tbl tbody').innerHTML = DATA.counties.map(c =>
  `<tr><td>${{c.county}}</td><td>${{c.de}}</td><td>${{c.adj}}</td><td>${{Math.round(c.miles)}}</td></tr>`).join('');
</script>
</body></html>"""

(ROOT / "va_map.html").write_text(html)
print(f"wrote va_map.html: {len(counties)} counties/cities, {de_total} DE ads, {de_100} within 100 mi, {unmapped} unmapped")
print(counties.head(8).to_string(index=False))


# --- Dashboard map data (10/17) -------------------------------------------------------------
# Aggregated county counts only (no ad text), for the map panel on tommyaliff.com/job-market.
SITE_JSON = pathlib.Path.home() / "githubio" / "taliff0001.github.io" / "assets" / "data" / "va-map.json"
de_counties = counties[counties["de"] > 0][["county", "lat", "lon", "de"]].round({"lat": 4, "lon": 4})
SITE_JSON.write_text(json.dumps({
    "source": "Adzuna API, 90 days to " + last,
    "de_total": de_total, "de_unmapped": int(((va["kind"] == "DE") & va["county"].isna()).sum()),
    "counties": de_counties.to_dict("records"),
}, indent=1))
print(f"wrote {SITE_JSON} ({len(de_counties)} counties with DE postings)")
