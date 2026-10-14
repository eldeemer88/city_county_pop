"""Local search tool for the city/county population graphs.

Usage:   python app/serve.py [--port 8765] [--no-browser]
Then open http://127.0.0.1:8765 (it opens automatically).

Uses only the Python standard library. Reads output/city_pop.db read-only and
listens on 127.0.0.1 only, so nothing is exposed to the network.
"""
import argparse
import csv
import io
import json
import re
import sqlite3
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DB = Path(__file__).resolve().parents[1] / "output" / "city_pop.db"


def connect():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def has_fts(con):
    try:
        con.execute("SELECT 1 FROM city_search LIMIT 1")
        return True
    except sqlite3.OperationalError:  # FTS5 missing in this SQLite build
        return False


def search(con, q="", state="", sort="rank", share_min=None, share_max=None):
    sql = "SELECT c.* FROM cities c"
    where, args = [], []
    q = (q or "").strip()
    if q:
        terms = re.findall(r"[\w\-']+", q)
        if terms and has_fts(con):
            fts = " ".join(f'"{t}"*' for t in terms)
            sql += " JOIN city_search s ON s.city_id = c.city_id"
            where.append("city_search MATCH ?")
            args.append(fts)
        elif terms:  # plain substring fallback, every term must match somewhere
            sql += " JOIN search_index s ON s.city_id = c.city_id"
            for t in terms:
                where.append("(s.city || ' ' || s.state || ' ' || s.counties || ' ' || s.notes) LIKE ?")
                args.append(f"%{t}%")
    if state:
        where.append("c.state = ?")
        args.append(state)
    if share_min not in (None, ""):
        where.append("c.share_2020 >= ?")
        args.append(float(share_min))
    if share_max not in (None, ""):
        where.append("c.share_2020 <= ?")
        args.append(float(share_max))
    if where:
        sql += " WHERE " + " AND ".join(where)
    order = {"rank": "c.rank", "name": "c.city", "share": "c.share_2020",
             "share_desc": "c.share_2020 DESC", "peak": "c.peak_share DESC"}.get(sort, "c.rank")
    sql += f" ORDER BY {order}"
    return [dict(r) for r in con.execute(sql, args)]


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>City vs County Population</title>
<style>
:root{--bg:#f6f5f2;--surface:#fff;--ink:#141413;--ink2:#5a5955;--line:#e2e0da;--accent:#2a78d6;--accent2:#eb6834}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--surface:#1f1f1e;--ink:#f0efec;--ink2:#b5b3ab;--line:#33322f;--accent:#3987e5;--accent2:#d95926}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:20px 24px 8px;max-width:1400px;margin:auto}h1{font-size:22px;margin:0 0 4px}header p{margin:0;color:var(--ink2);font-size:14px}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:12px 24px;max-width:1400px;margin:auto}
input,select,button,textarea{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:7px 10px}
#q{flex:1;min-width:220px}button{cursor:pointer}button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.tabs{display:flex;gap:6px;margin-left:auto}
main{max-width:1400px;margin:auto;padding:4px 24px 40px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;cursor:pointer;transition:transform .1s}
.card:hover{transform:translateY(-2px);border-color:var(--accent)}
.card img{width:100%;display:block;background:#fff;aspect-ratio:12/6.6;object-fit:cover}
.card .m{padding:10px 12px}.card b{font-size:15px}.meta{color:var(--ink2);font-size:13px}
.pill{display:inline-block;font-size:12px;padding:1px 8px;border-radius:99px;background:var(--bg);border:1px solid var(--line);margin-right:4px}
#detail{display:none}#detail img{width:100%;max-width:1200px;background:#fff;border-radius:8px;border:1px solid var(--line)}
table{border-collapse:collapse;width:100%;font-size:13px;background:var(--surface)}th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:right}
th{position:sticky;top:0;background:var(--surface)}td.l,th.l{text-align:left}.tw{max-height:520px;overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:12px}
.notes{color:var(--ink2);font-size:13px;max-width:1200px}a{color:var(--accent)}
#sql{display:none}#sqlq{width:100%;min-height:90px;font-family:ui-monospace,Menlo,monospace;font-size:13px}
.count{color:var(--ink2);font-size:13px;margin:0 0 10px}
#averages{display:none}#averages img{width:100%;max-width:1200px;background:#fff;border-radius:8px;border:1px solid var(--line);display:block;margin:10px 0}
.seg{display:inline-flex;gap:0}.seg button{border-radius:0;margin-left:-1px}.seg button:first-child{border-radius:8px 0 0 8px}.seg button:last-child{border-radius:0 8px 8px 0}
.ctl{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:6px 0 4px}h3{margin:22px 0 2px;font-size:17px}
@media (max-width:600px){header,.bar,main{padding-left:16px;padding-right:16px}.grid{grid-template-columns:1fr}}
</style></head><body>
<header><h1>City vs. county population, 1800–2020</h1>
<p>Top 100 cities in the contiguous U.S. by 2020 Census population: city-limits population, county population and the city's share of its county, decennial census counts.</p></header>
<div class="bar">
 <span id="filters" style="display:contents"><input id="q" placeholder="Search city, state, county or notes (e.g. Texas, Arapahoe, consolidated)…" autofocus>
 <select id="state"><option value="">All states</option></select>
 <select id="sort"><option value="rank">Sort: 2020 rank</option><option value="name">Sort: name</option>
  <option value="share">Sort: 2020 share ↑</option><option value="share_desc">Sort: 2020 share ↓</option><option value="peak">Sort: peak share ↓</option></select>
 <label class="meta">2020 share % <input id="smin" type="number" min="0" max="100" style="width:70px" placeholder="min"> – <input id="smax" type="number" min="0" max="100" style="width:70px" placeholder="max"></label></span>
 <div class="tabs"><button id="tBrowse" class="on">Browse</button><button id="tAvg">Averages</button><button id="tSize">City Size</button><button id="tSql">SQL</button></div>
</div>
<main>
 <section id="browse"><p class="count" id="count"></p><div class="grid" id="grid"></div></section>
 <section id="detail"></section>
 <section id="averages">
  <h2 style="margin:4px 0" id="aggTitle">National and regional averages</h2>
  <p class="meta"><span id="aggIntro">Averages across the top-100 cities, nationally and by U.S. Census region.</span> Each year uses the cities with both a city and a county count that year (n under each year). <b>Unweighted</b>: simple mean of city shares. <b>Population-weighted</b>: shares weighted by county population, i.e. total city population ÷ total county population (the ratio of the two bars).</p>
  <div class="ctl"><span class="meta" id="segLabel">Region</span><span class="seg" id="segRegion"></span>
   <span class="meta">Weighting</span><span class="seg" id="segW"><button data-w="unweighted" class="on">Unweighted</button><button data-w="weighted">Population-weighted</button></span></div>
  <p class="meta"><a id="aggPng" href="#" download>Download PNG</a> · <a id="aggCsv" href="#">Download data (CSV)</a> · <a id="aggPdf" href="/averages.pdf">All charts in this section (PDF)</a></p>
  <img id="aggImg" alt="Average chart">
  <h3 id="cmpTitle">Average share of county population: national and the four regions</h3>
  <img id="cmpImg" alt="Share comparison chart">
  <p class="notes" id="aggMembers"></p>
  <div class="tw"><table><thead><tr><th>Year</th><th>n cities</th><th>Mean city pop.</th><th>Mean county pop.</th><th>Share %</th></tr></thead><tbody id="aggRows"></tbody></table></div>
 </section>
 <section id="sql"><p class="meta">Read-only SQL against <code>city_pop.db</code>. Tables: <code>cities</code>, <code>observations</code>, <code>graphs</code> (PNG blobs; don't select <code>png</code>), <code>sources</code>, <code>aggregates</code>, <code>city_regions</code>, <code>city_size</code>, <code>agg_graphs</code>, <code>city_search</code> (FTS5).</p>
  <textarea id="sqlq">SELECT city, year, city_pop, county_pop, share_pct, county_label
FROM observations WHERE city_id = 'detroit_mi' ORDER BY year;</textarea>
  <p><button id="run">Run query</button> <a id="sqlcsv" href="#">Download result as CSV</a></p><div id="sqlout"></div></section>
</main>
<script>
const $=s=>document.querySelector(s);const fmt=n=>n==null?'—':Number(n).toLocaleString();
let timer;
async function load(){
 const p=new URLSearchParams({q:$('#q').value,state:$('#state').value,sort:$('#sort').value,smin:$('#smin').value,smax:$('#smax').value});
 const r=await fetch('/api/search?'+p);const d=await r.json();
 $('#count').textContent=d.length+' of 100 cities';
 $('#grid').innerHTML=d.map(c=>`<div class="card" data-id="${c.city_id}"><img loading="lazy" src="/graph/${c.city_id}.png?scale=linear" alt="${c.city} chart">
 <div class="m"><b>#${c.rank} ${c.city}, ${c.state}</b><div class="meta">${fmt(c.pop_2020)} (2020) · ${c.county_2020}</div>
 <div class="meta"><span class="pill">2020 share ${c.share_2020.toFixed(1)}%</span><span class="pill">peak ${c.peak_share.toFixed(0)}% (${c.peak_share_year})</span></div></div></div>`).join('');
 document.querySelectorAll('.card').forEach(e=>e.onclick=()=>{location.hash=e.dataset.id});
}
async function detail(id){
 const d=await (await fetch('/api/city/'+id)).json();const c=d.city;
 $('#detail').innerHTML=`<p><a href="#" id="back">← All cities</a></p>
 <h2 style="margin:4px 0">#${c.rank} ${c.city}, ${c.state_name}</h2>
 <p class="meta">2020 population ${fmt(c.pop_2020)} · comparison county: ${c.county_2020} · 2020 share ${c.share_2020.toFixed(1)}% · peak share ${c.peak_share.toFixed(1)}% in ${c.peak_share_year}</p>
 <p><button id="lin" class="on">Linear scale</button> <button id="log">Log scale</button>
  <a href="/graph/${id}.png?scale=linear" download="${id}.png">Download PNG</a> · <a href="/api/city/${id}.csv">Download data (CSV)</a></p>
 <img id="big" src="/graph/${id}.png?scale=linear" alt="chart">
 <p class="notes">${c.city_notes||''}</p>
 <div class="tw"><table><thead><tr><th>Year</th><th>City pop.</th><th>County pop.</th><th>Share %</th><th class="l">Comparison county</th><th class="l">Basis</th><th class="l">City source</th><th class="l">County source</th></tr></thead><tbody>
 ${d.obs.map(o=>`<tr><td>${o.year}</td><td>${fmt(o.city_pop)}</td><td>${fmt(o.county_pop)}</td><td>${o.share_pct==null?'—':o.share_pct.toFixed(1)}</td><td class="l">${o.county_label}</td><td class="l">${o.county_basis}</td><td class="l">${o.city_source||''}</td><td class="l">${o.county_source||''}</td></tr>`).join('')}
 </tbody></table></div>`;
 $('#back').onclick=e=>{e.preventDefault();location.hash=''};
 $('#lin').onclick=()=>{$('#big').src=`/graph/${id}.png?scale=linear`;$('#lin').className='on';$('#log').className=''};
 $('#log').onclick=()=>{$('#big').src=`/graph/${id}.png?scale=log`;$('#log').className='on';$('#lin').className=''};
 window.scrollTo(0,0);
}
const SCHEMES={
 region:{title:'National and regional averages',intro:'Averages across the top-100 cities, nationally and by U.S. Census region.',
  seg:'Region',prefix:'agg',compare:'compare',pdf:'/averages.pdf',cmp:'Average share of county population: national and the four regions',
  groups:[['National','National'],['Northeast','Northeast'],['Midwest','Midwest'],['South','South'],['West','West']]},
 size:{title:'City size: averages by land-area quartile',intro:'Averages across the top-100 cities grouped into quartiles of 2020 land area (25 cities each). Quartiles use 2020 boundaries for every year, so they group cities by today\'s size, not their size at the time.',
  seg:'Land area',prefix:'size',compare:'size_compare',pdf:'/city_size.pdf',cmp:'Average share of county population: all cities and the four land-area quartiles',
  groups:[['National','All cities'],['Q1','Q1 (smallest)'],['Q2','Q2'],['Q3','Q3'],['Q4','Q4 (largest)']]}};
let aggS='region',aggG='National',aggW='unweighted';
function show(id){['browse','detail','sql','averages'].forEach(k=>$('#'+k).style.display=k===id?'block':'none');
 $('#tBrowse').className=(id==='browse'||id==='detail')?'on':'';$('#tSql').className=id==='sql'?'on':'';
 $('#tAvg').className=(id==='averages'&&aggS==='region')?'on':'';$('#tSize').className=(id==='averages'&&aggS==='size')?'on':'';
 $('#filters').style.display=id==='browse'?'contents':'none'}
function setScheme(k){if(aggS!==k){aggS=k;aggG='National'}const S=SCHEMES[k];
 $('#aggTitle').textContent=S.title;$('#aggIntro').textContent=S.intro;$('#segLabel').textContent=S.seg;$('#cmpTitle').textContent=S.cmp;$('#aggPdf').href=S.pdf;
 $('#segRegion').innerHTML=S.groups.map(([g,l])=>`<button data-g="${g}">${l}</button>`).join('');
 document.querySelectorAll('#segRegion button').forEach(b=>b.onclick=()=>{aggG=b.dataset.g;renderAvg()})}
async function renderAvg(){const S=SCHEMES[aggS];
 const name=`${S.prefix}_${aggG.toLowerCase()}_${aggW}`;
 $('#aggImg').src=`/agg_graph/${name}.png`;$('#cmpImg').src=`/agg_graph/${S.compare}_${aggW}.png`;
 $('#aggPng').href=`/agg_graph/${name}.png`;$('#aggPng').download=name+'.png';
 $('#aggCsv').href=`/api/aggregates.csv?scheme=${aggS}&group=${aggG}&weighting=${aggW}`;
 document.querySelectorAll('#segRegion button').forEach(b=>b.className=b.dataset.g===aggG?'on':'');
 document.querySelectorAll('#segW button').forEach(b=>b.className=b.dataset.w===aggW?'on':'');
 const d=await (await fetch(`/api/aggregates?scheme=${aggS}&group=${aggG}&weighting=${aggW}`)).json();
 const gl=S.groups.find(x=>x[0]===aggG)[1];
 $('#aggMembers').textContent=`${aggG==='National'?'All':gl} cities (${d.members.length}): `+d.members.join(', ')+'.';
 $('#aggRows').innerHTML=d.rows.map(r=>`<tr><td>${r.year}</td><td>${r.n_cities}</td><td>${fmt(r.mean_city_pop)}</td><td>${fmt(r.mean_county_pop)}</td><td>${r.share_pct==null?'—':r.share_pct.toFixed(1)}</td></tr>`).join('')}
function route(){const h=location.hash.slice(1);
 if(h==='sql'){show('sql');return}
 if(h==='averages'||h==='citysize'){setScheme(h==='citysize'?'size':'region');show('averages');renderAvg();return}
 if(h){show('detail');detail(h)}else{show('browse')}}
async function runSql(){const q=$('#sqlq').value;const r=await fetch('/api/sql',{method:'POST',body:q});const d=await r.json();
 if(d.error){$('#sqlout').innerHTML=`<p style="color:var(--accent2)">${d.error}</p>`;return}
 $('#sqlout').innerHTML=`<p class="meta">${d.rows.length} rows</p><div class="tw"><table><thead><tr>${d.cols.map(c=>`<th class="l">${c}</th>`).join('')}</tr></thead><tbody>${d.rows.map(r=>`<tr>${r.map(v=>`<td class="l">${v==null?'':v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
(async()=>{const st=await (await fetch('/api/states')).json();$('#state').innerHTML+=st.map(s=>`<option value="${s.state}">${s.state_name}</option>`).join('');
 ['#q','#smin','#smax'].forEach(s=>$(s).oninput=()=>{clearTimeout(timer);timer=setTimeout(load,150)});
 ['#state','#sort'].forEach(s=>$(s).onchange=load);
 $('#tBrowse').onclick=()=>{location.hash=''};$('#tSql').onclick=()=>{location.hash='sql'};$('#tAvg').onclick=()=>{location.hash='averages'};$('#tSize').onclick=()=>{location.hash='citysize'};
 document.querySelectorAll('#segW button').forEach(b=>b.onclick=()=>{aggW=b.dataset.w;renderAvg()});
 $('#run').onclick=runSql;$('#sqlcsv').onclick=e=>{e.preventDefault();location.href='/api/sql.csv?q='+encodeURIComponent($('#sqlq').value)};
 window.onhashchange=route;await load();route();})();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    con = None

    def log_message(self, *a):
        pass

    def send(self, body, ctype="application/json", code=200, extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def run_sql(self, q):
        q = q.strip().rstrip(";")
        if not re.match(r"(?is)^\s*(select|with|pragma\s+table_info)\b", q) or ";" in q:
            raise ValueError("Only a single read-only SELECT / WITH query is allowed.")
        cur = self.con.execute(q)
        cols = [c[0] for c in cur.description]
        rows = [["<blob>" if isinstance(v, bytes) else v for v in r] for r in cur.fetchmany(5000)]
        return cols, rows

    def do_GET(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.send(PAGE, "text/html; charset=utf-8")
            if u.path == "/api/search":
                return self.send(json.dumps(search(self.con, qs.get("q"), qs.get("state"), qs.get("sort", "rank"),
                                                   qs.get("smin"), qs.get("smax"))))
            if u.path == "/api/states":
                rows = self.con.execute("SELECT DISTINCT state, state_name FROM cities ORDER BY state_name")
                return self.send(json.dumps([dict(r) for r in rows]))
            m = re.match(r"^/api/city/([\w]+)(\.csv)?$", u.path)
            if m:
                cid = m.group(1)
                city = self.con.execute("SELECT * FROM cities WHERE city_id=?", (cid,)).fetchone()
                if not city:
                    return self.send('{"error":"not found"}', code=404)
                obs = [dict(r) for r in self.con.execute(
                    "SELECT * FROM observations WHERE city_id=? ORDER BY year", (cid,))]
                if m.group(2):
                    buf = io.StringIO()
                    w = csv.DictWriter(buf, fieldnames=list(obs[0].keys()))
                    w.writeheader()
                    w.writerows(obs)
                    return self.send(buf.getvalue(), "text/csv",
                                     extra={"Content-Disposition": f'attachment; filename="{cid}.csv"'})
                return self.send(json.dumps({"city": dict(city), "obs": obs}))
            m = re.match(r"^/graph/([\w]+)\.png$", u.path)
            if m:
                row = self.con.execute("SELECT png FROM graphs WHERE city_id=? AND scale=?",
                                       (m.group(1), qs.get("scale", "linear"))).fetchone()
                if not row:
                    return self.send(b"", "image/png", 404)
                return self.send(row[0], "image/png", extra={"Cache-Control": "max-age=3600"})
            if u.path in ("/api/aggregates", "/api/aggregates.csv"):
                sch = qs.get("scheme", "region")
                g, wt = qs.get("group", "National"), qs.get("weighting", "unweighted")
                rows = [dict(r) for r in self.con.execute(
                    'SELECT scheme, "group", weighting, year, n_cities, mean_city_pop, mean_county_pop, share_pct '
                    'FROM aggregates WHERE scheme=? AND "group"=? AND weighting=? ORDER BY year', (sch, g, wt))]
                if u.path.endswith(".csv"):
                    buf = io.StringIO()
                    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
                    w.writeheader()
                    w.writerows(rows)
                    return self.send(buf.getvalue(), "text/csv", extra={
                        "Content-Disposition": f'attachment; filename="averages_{sch}_{g.lower()}_{wt}.csv"'})
                if sch == "size":
                    q = ("SELECT c.city, c.state FROM cities c JOIN city_size r USING(city_id) "
                         + ("" if g == "National" else "WHERE r.size_quartile=? ") + "ORDER BY c.rank")
                else:
                    q = ("SELECT c.city, c.state FROM cities c JOIN city_regions r USING(city_id) "
                         + ("" if g == "National" else "WHERE r.region=? ") + "ORDER BY c.rank")
                members = [f"{r[0]}, {r[1]}" for r in self.con.execute(q, () if g == "National" else (g,))]
                return self.send(json.dumps({"rows": rows, "members": members}))
            m = re.match(r"^/agg_graph/([\w]+)\.png$", u.path)
            if m:
                row = self.con.execute("SELECT png FROM agg_graphs WHERE name=?", (m.group(1),)).fetchone()
                if not row:
                    return self.send(b"", "image/png", 404)
                return self.send(row[0], "image/png", extra={"Cache-Control": "max-age=3600"})
            if u.path in ("/averages.pdf", "/city_size.pdf"):
                pdf = DB.parent / "graphs" / u.path.lstrip("/")
                if not pdf.exists():
                    return self.send('{"error":"PDF not found"}', code=404)
                return self.send(pdf.read_bytes(), "application/pdf",
                                 extra={"Content-Disposition": f'inline; filename="{pdf.name}"'})
            if u.path == "/api/sql.csv":
                cols, rows = self.run_sql(qs.get("q", ""))
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(cols)
                w.writerows(rows)
                return self.send(buf.getvalue(), "text/csv",
                                 extra={"Content-Disposition": 'attachment; filename="query.csv"'})
            return self.send('{"error":"not found"}', code=404)
        except Exception as e:
            return self.send(json.dumps({"error": str(e)}), code=400)

    def do_POST(self):
        if urlparse(self.path).path != "/api/sql":
            return self.send('{"error":"not found"}', code=404)
        q = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        try:
            cols, rows = self.run_sql(q)
            return self.send(json.dumps({"cols": cols, "rows": rows}))
        except Exception as e:
            return self.send(json.dumps({"error": str(e)}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if not DB.exists():
        sys.exit(f"Database not found at {DB}. Run `python run_all.py` first.")
    Handler.con = connect()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}"
    print(f"City population explorer running at {url}  (Ctrl+C to stop)")
    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
