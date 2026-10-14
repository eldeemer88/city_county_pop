"""Step 5: export the whole app as ONE self-contained HTML file.

    docs/index.html

All data (city panel, averages, notes, sources) is embedded as JSON and the
charts are drawn in the browser as SVG, so the file
  * opens offline by double-clicking (no Python, no server, no internet), and
  * can be published for free with GitHub Pages (serve the /docs folder).

It reproduces the local app's Browse, city detail (linear/log), Averages and
City Size views; the SQL tab is replaced by CSV downloads of the same tables.
"""
import json
from datetime import date

import numpy as np
import pandas as pd

from config import CONFIG, PROCESSED, ROOT, YEARS
from make_aggregates import (QUARTILES, REGIONS, STATE_REGION, WEIGHTINGS, group_notes,
                             make_schemes, size_quartiles)
from make_graphs import city_footnotes

OUT = ROOT / "docs" / "index.html"


def clean(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    return v


def build_data():
    panel = pd.read_csv(PROCESSED / "panel.csv")
    cities = pd.read_csv(CONFIG / "cities.csv")
    agg = pd.read_csv(PROCESSED / "aggregates.csv")
    q = size_quartiles().set_index("city_id")
    from build_db import STATE_NAMES

    strings, sidx = [], {}

    def S(v):
        v = clean(v)
        if v is None or v == "":
            return -1
        if v not in sidx:
            sidx[v] = len(strings)
            strings.append(v)
        return sidx[v]

    city_rows, obs = [], {}
    for c in cities.itertuples():
        p = panel[panel.city_id == c.city_id].sort_values("year").set_index("year").reindex(YEARS)
        first = {"city_notes": c.city_notes if isinstance(c.city_notes, str) else "",
                 "extends_beyond_principal_county": c.extends_beyond_principal_county}
        valid = p.dropna(subset=["share_pct"])
        peak_year = int(valid.share_pct.idxmax()) if len(valid) else None
        city_rows.append(dict(
            id=c.city_id, rank=int(c.rank), city=c.city, state=c.state, stateName=STATE_NAMES[c.state],
            pop2020=int(c.pop_2020), county2020=p.loc[2020, "county_label"],
            share2020=clean(p.loc[2020, "share_pct"]),
            peak=clean(valid.share_pct.max()) if len(valid) else None, peakYear=peak_year,
            region=STATE_REGION[c.state], quartile=q.loc[c.city_id, "group"],
            area=float(q.loc[c.city_id, "land_area_sqmi_2020"]),
            notes=first["city_notes"], foot=city_footnotes(first, p.reset_index()),
            search=" ".join([c.city, c.state, STATE_NAMES[c.state], " ".join(p.county_label.dropna().unique()),
                             first["city_notes"]] + [n for n in p.county_note.dropna().unique()]).lower()))
        obs[c.city_id] = dict(
            c=[clean(v) for v in p.city_pop], k=[clean(v) for v in p.county_pop],
            s=[clean(v) for v in p.share_pct], lab=[S(v) for v in p.county_label],
            basis=[S(v) for v in p.county_basis], keys=[S(v) for v in p.county_keys],
            note=[S(v) for v in p.county_note], csrc=[S(v) for v in p.city_source],
            ksrc=[S(v) for v in p.county_source])

    schemes = make_schemes()
    cities_sorted = cities.sort_values("rank")
    scheme_out = {}
    for skey, sc in schemes.items():
        if skey == "region":
            member_of = cities_sorted.state.map(STATE_REGION)
        else:
            member_of = cities_sorted.city_id.map(q["group"])
        groups = ["National"] + sc["groups"]
        members = {g: [f"{r.city}, {r.state}" for r in
                       (cities_sorted if g == "National" else cities_sorted[member_of == g]).itertuples()]
                   for g in groups}
        series = {}
        for g in groups:
            series[g] = {}
            for w in WEIGHTINGS:
                d = agg[(agg.scheme == skey) & (agg.group == g) & (agg.weighting == w)].set_index("year").reindex(YEARS)
                series[g][w] = dict(n=[clean(v) for v in d.n_cities], mc=[clean(v) for v in d.mean_city_pop],
                                    mk=[clean(v) for v in d.mean_county_pop], s=[clean(v) for v in d.share_pct])
        scheme_out[skey] = dict(
            groups=groups,
            title={g: sc["title"](g) for g in groups},
            scope={g: sc["scope"](g, len(members[g])) for g in groups},
            legend={g: (("All cities" if skey == "size" else "National") if g == "National" else sc["names"][g])
                    for g in groups},
            button={g: ("All cities" if skey == "size" else "National") if g == "National" else
                    ({"Q1": "Q1 (smallest)", "Q4": "Q4 (largest)"}.get(g, g) if skey == "size" else g)
                    for g in groups},
            colors=sc["colors"], members=members, series=series,
            foot={g: {w: group_notes(members[g], g, w, sc) for w in WEIGHTINGS} for g in groups},
            compareTitle=sc["compare_title"], dashedAll=(skey == "size"))

    return dict(years=YEARS, strings=strings, cities=city_rows, obs=obs, schemes=scheme_out,
                weightings=WEIGHTINGS, generated=date.today().isoformat())


def main():
    data = build_data()
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("/*__DATA__*/null", payload)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"[static] wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>City vs County Population</title>
<meta name="description" content="City-limits vs county population for the 100 largest contiguous-U.S. cities, decennial censuses 1800-2020.">
<style>
:root{--bg:#f6f5f2;--surface:#ffffff;--ink:#141413;--ink2:#5a5955;--line:#e2e0da;--grid:#e8e7e3;--accent:#2a78d6;
 --city:#2a78d6;--county:#b4c6df;--share:#eb6834;
 --g-national:#141413;--g-northeast:#2a78d6;--g-midwest:#eb6834;--g-south:#1baf7a;--g-west:#eda100;
 --g-all:#eb6834;--q1:#86b6ef;--q2:#3987e5;--q3:#1c5cab;--q4:#0d366b;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--surface:#1f1f1e;--ink:#f0efec;--ink2:#b5b3ab;--line:#33322f;--grid:#2c2b29;--accent:#3987e5;
 --city:#3987e5;--county:#4a5a73;--share:#d95926;--g-national:#f0efec;--g-northeast:#3987e5;--g-midwest:#d95926;--g-south:#199e70;--g-west:#c98500;
 --g-all:#d95926;--q1:#1c5cab;--q2:#3987e5;--q3:#6da7ec;--q4:#b7d3f6;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#161615;--surface:#1f1f1e;--ink:#f0efec;--ink2:#b5b3ab;--line:#33322f;--grid:#2c2b29;--accent:#3987e5;
 --city:#3987e5;--county:#4a5a73;--share:#d95926;--g-national:#f0efec;--g-northeast:#3987e5;--g-midwest:#d95926;--g-south:#199e70;--g-west:#c98500;
 --g-all:#d95926;--q1:#1c5cab;--q2:#3987e5;--q3:#6da7ec;--q4:#b7d3f6;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:20px 24px 6px;max-width:1300px;margin:auto}h1{font-size:22px;margin:0 0 4px}header p{margin:0;color:var(--ink2);font-size:14px}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:12px 24px;max-width:1300px;margin:auto}
input,select,button{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:7px 10px}
#q{flex:1;min-width:220px}button{cursor:pointer}button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.tabs{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap}
main{max-width:1300px;margin:auto;padding:4px 24px 40px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;cursor:pointer;transition:transform .1s}
.card:hover{transform:translateY(-2px);border-color:var(--accent)}.card svg{display:block;width:100%;height:auto}
.card .m{padding:8px 12px 10px}.card b{font-size:15px}.meta{color:var(--ink2);font-size:13px}
.pill{display:inline-block;font-size:12px;padding:1px 8px;border-radius:99px;background:var(--bg);border:1px solid var(--line);margin-right:4px}
.chartbox{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:6px;margin:10px 0}
.chartbox svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:12.5px;
 box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;min-width:180px;z-index:5}.tip b{font-size:13px}.tip .r{display:flex;justify-content:space-between;gap:14px}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-size:13px;background:var(--surface)}th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:right}
th{position:sticky;top:0;background:var(--surface)}td.l,th.l{text-align:left}.tw{max-height:520px;overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:12px}
.notes{color:var(--ink2);font-size:13px}a{color:var(--accent)}a.btn{cursor:pointer}
.seg{display:inline-flex}.seg button{border-radius:0;margin-left:-1px}.seg button:first-child{border-radius:8px 0 0 8px;margin-left:0}.seg button:last-child{border-radius:0 8px 8px 0}
.ctl{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:8px 0}h2{margin:4px 0;font-size:20px}h3{margin:22px 0 2px;font-size:17px}
.count{color:var(--ink2);font-size:13px;margin:0 0 10px}section{display:none}
footer{max-width:1300px;margin:auto;padding:0 24px 30px;color:var(--ink2);font-size:12px}
@media (max-width:640px){header,.bar,main,footer{padding-left:16px;padding-right:16px}.grid{grid-template-columns:1fr}.tabs{margin-left:0}}
</style></head><body>
<header><h1>City vs. county population, 1800–2020</h1>
<p>The 100 largest cities in the contiguous U.S. (2020 Census): population inside city limits, population of the surrounding county, and the city's share of its county, from decennial census counts.</p></header>
<div class="bar">
 <span id="filters" style="display:contents">
 <input id="q" placeholder="Search city, state, county or notes (e.g. Texas, Arapahoe, consolidated)…">
 <select id="state"><option value="">All states</option></select>
 <select id="sort"><option value="rank">Sort: 2020 rank</option><option value="name">Sort: name</option>
  <option value="share">Sort: 2020 share ↑</option><option value="share_desc">Sort: 2020 share ↓</option><option value="peak">Sort: peak share ↓</option><option value="area">Sort: land area ↓</option></select>
 <label class="meta">2020 share % <input id="smin" type="number" min="0" max="100" style="width:68px" placeholder="min"> – <input id="smax" type="number" min="0" max="100" style="width:68px" placeholder="max"></label>
 </span>
 <div class="tabs"><button id="tBrowse">Browse</button><button id="tAvg">Averages</button><button id="tSize">City Size</button><button id="tData">Data</button></div>
</div>
<main>
 <section id="browse"><p class="count" id="count"></p><div class="grid" id="grid"></div></section>
 <section id="detail"></section>
 <section id="averages">
  <h2 id="aggTitle"></h2>
  <p class="meta"><span id="aggIntro"></span> Each year uses the cities with both a city and a county count that year (n under each year). <b>Unweighted</b>: simple mean of city shares. <b>Population-weighted</b>: shares weighted by county population, i.e. total city population ÷ total county population (the ratio of the two bars).</p>
  <div class="ctl"><span class="meta" id="segLabel"></span><span class="seg" id="segGroup"></span>
   <span class="meta">Weighting</span><span class="seg" id="segW"><button data-w="unweighted">Unweighted</button><button data-w="weighted">Population-weighted</button></span></div>
  <p class="meta"><a class="btn" id="aggPng">Download PNG</a> · <a class="btn" id="aggSvg">SVG</a> · <a class="btn" id="aggCsv">Data (CSV)</a></p>
  <div class="chartbox" id="aggBox"></div>
  <h3 id="cmpTitle"></h3>
  <p class="meta"><a class="btn" id="cmpPng">Download PNG</a> · <a class="btn" id="cmpSvg">SVG</a></p>
  <div class="chartbox" id="cmpBox"></div>
  <p class="notes" id="aggMembers"></p>
  <div class="tw"><table><thead><tr><th>Year</th><th>n cities</th><th>Mean city pop.</th><th>Mean county pop.</th><th>Share %</th></tr></thead><tbody id="aggRows"></tbody></table></div>
 </section>
 <section id="data">
  <h2>Download the data</h2>
  <p class="meta">Everything in this page is built from these tables. The full project (Python code, raw sources, SQLite database, PDFs) is in the project repository.</p>
  <ul>
   <li><a class="btn" id="dlPanel">City × census-year panel (CSV)</a>: city and county populations, share, comparison county, sources.</li>
   <li><a class="btn" id="dlCities">Cities (CSV)</a>: rank, 2020 population, region, land area and quartile, notes.</li>
   <li><a class="btn" id="dlAgg">Averages (CSV)</a>: national, regional and land-area-quartile averages, both weightings.</li>
  </ul>
  <h3>Definitions</h3>
  <p class="notes">City population: Stanford CESTA compilation of U.S. Census Bureau place counts (1800–2010) and the 2020 Census. County population: Census county file 1900–2020 (van Leuven) and Forstall (1996), <i>Population of States and Counties of the United States: 1790–1990</i>, for 1800–1890. The comparison county is the county (or county-equivalent) containing the city at each census; where it changes, the city chart marks the year with a dashed rule. Cities extending into other counties are compared with their principal county, which overstates the share somewhat. CESTA records places below the 2,500 reporting threshold as 0; these are shown as missing.</p>
 </section>
</main>
<footer id="foot"></footer>
<script>
const DATA=/*__DATA__*/null;
const Y=DATA.years, NY=Y.length, STR=DATA.strings, $=s=>document.querySelector(s);
const st=i=>i<0?'':STR[i];
const fmt=n=>n==null?'—':Math.round(n).toLocaleString('en-US');
const CITY=Object.fromEntries(DATA.cities.map(c=>[c.id,c]));
function css(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim()}
function C(){return{ink:css('--ink'),ink2:css('--ink2'),grid:css('--grid'),surf:css('--surface'),city:css('--city'),county:css('--county'),share:css('--share')}}
function fmtPop(x){if(x>=1e6){const v=x/1e6;return (Math.abs(v-Math.round(v))<1e-9?Math.round(v):v.toFixed(1))+'M'}if(x>=1e3)return Math.round(x/1e3)+'K';return String(Math.round(x))}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function wrap(text,max){const out=[];let line='';for(const w of text.split(' ')){if((line+' '+w).trim().length>max){if(line)out.push(line);line=w}else line=(line+' '+w).trim()}if(line)out.push(line);return out}
function niceTicks(max,count){if(!(max>0))return[0,1];const raw=max/count,mag=Math.pow(10,Math.floor(Math.log10(raw))),r=raw/mag;
 const step=(r<=1?1:r<=2?2:r<=2.5?2.5:r<=5?5:10)*mag;const t=[];for(let v=0;v<=max*1.0001+step;v+=step){t.push(v);if(v>=max)break}return t}
function svgEl(w,h){return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" font-family="system-ui,-apple-system,Segoe UI,sans-serif">`}
const T=(x,y,s,o={})=>`<text x="${x}" y="${y}" font-size="${o.size||13}" fill="${o.fill}" ${o.bold?'font-weight="700"':''} text-anchor="${o.anchor||'start'}" ${o.rot?`transform="rotate(${o.rot} ${x} ${y})"`:''}>${esc(s)}</text>`;

/* ---------- bar + share chart (city or group average) ---------- */
function barShareChart(o){
 // o: {title, subtitle, legend:[city,county,share], city[], county[], share[], log, xlab(i)->[l1,l2?], changes:[{i,label}], foot[], tip(i)->html}
 const c=C(), W=1200, L=90, R=1100, top=160, PH=380;
 const foot=[];o.foot.forEach(n=>wrap(n,185).forEach(l=>foot.push(l)));
 const xlabH=o.twoLine?44:52, H=top+PH+xlabH+16+foot.length*16+8;
 const bw=(R-L)/NY, xc=i=>L+bw*(i+0.5), b=bw*0.38;
 const vals=[...o.city,...o.county].filter(v=>v!=null&&v>0);
 const vmax=vals.length?Math.max(...vals):1;
 let yv, ticks, ymin=0;
 if(o.log){ymin=Math.pow(10,Math.floor(Math.log10(Math.max(1,Math.min(...vals)))));const ymx=Math.pow(10,Math.ceil(Math.log10(vmax)));
  ticks=[];for(let t=ymin;t<=ymx*1.0001;t*=10)ticks.push(t);yv=v=>top+PH-(Math.log10(v)-Math.log10(ymin))/(Math.log10(ymx)-Math.log10(ymin))*PH}
 else{ticks=niceTicks(vmax,5);const ymx=ticks[ticks.length-1];yv=v=>top+PH-v/ymx*PH}
 const shares=o.share.filter(v=>v!=null), smax=Math.max(100,...shares)*1.05, ys=v=>top+PH-v/smax*PH;
 let s=svgEl(W,H)+`<rect width="${W}" height="${H}" fill="${c.surf}"/>`;
 s+=T(L-15,36,o.title,{size:22,bold:1,fill:c.ink})+T(L-15,62,o.subtitle,{size:13.5,fill:c.ink2});
 // legend
 let lx=L-15;const ly=92;
 [[c.city,'rect',o.legend[0]],[c.county,'rect',o.legend[1]],[c.share,'line',o.legend[2]]].forEach(([col,k,lab])=>{
  s+= k==='rect'?`<rect x="${lx}" y="${ly-9}" width="22" height="11" fill="${col}"/>`:`<line x1="${lx}" y1="${ly-3.5}" x2="${lx+22}" y2="${ly-3.5}" stroke="${col}" stroke-width="2.5"/><circle cx="${lx+11}" cy="${ly-3.5}" r="3.5" fill="${col}" stroke="${c.surf}"/>`;
  s+=T(lx+30,ly,lab,{size:13,fill:c.ink});lx+=40+lab.length*7.1});
 // grid + left axis
 ticks.forEach(t=>{const y=yv(t);s+=`<line x1="${L}" x2="${R}" y1="${y}" y2="${y}" stroke="${c.grid}"/>`+T(L-8,y+4,fmtPop(t),{size:12,fill:c.ink2,anchor:'end'})});
 s+=`<line x1="${L}" x2="${L}" y1="${top}" y2="${top+PH}" stroke="${c.ink2}"/><line x1="${L}" x2="${R}" y1="${top+PH}" y2="${top+PH}" stroke="${c.ink2}"/>`;
 s+=T(28,top+PH/2,o.yTitle||'Population',{size:13,fill:c.ink2,anchor:'middle',rot:-90});
 // right axis
 for(let p=0;p<=smax;p+=20){const y=ys(p);s+=`<line x1="${R}" x2="${R+5}" y1="${y}" y2="${y}" stroke="${c.share}"/>`+T(R+9,y+4,p+'%',{size:12,fill:c.share})}
 s+=`<line x1="${R}" x2="${R}" y1="${top}" y2="${top+PH}" stroke="${c.share}"/>`+T(W-22,top+PH/2,'City share of county population',{size:13,fill:c.share,anchor:'middle',rot:-90});
 // bars
 for(let i=0;i<NY;i++){
  [[o.city[i],-1,c.city],[o.county[i],1,c.county]].forEach(([v,side,col])=>{if(v==null||v<=0)return;const y=yv(Math.max(v,ymin||0));
   const x=side<0?xc(i)-b:xc(i);s+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${b.toFixed(1)}" height="${(top+PH-y).toFixed(1)}" fill="${col}"/>`})}
 // x labels
 for(let i=0;i<NY;i++){const lab=o.xlab(i);if(o.twoLine){s+=T(xc(i),top+PH+18,lab[0],{size:11.5,fill:c.ink2,anchor:'middle'})+T(xc(i),top+PH+33,lab[1],{size:11,fill:c.ink2,anchor:'middle'})}
  else s+=T(xc(i)+4,top+PH+16,lab[0],{size:12,fill:c.ink2,anchor:'end',rot:-45})}
 // comparison-county change rules
 let prev=-99,lev=0;(o.changes||[]).forEach(ch=>{const x=L+bw*ch.i;lev=(ch.i-prev<=3)?lev+1:0;prev=ch.i;
  s+=`<line x1="${x}" x2="${x}" y1="${top}" y2="${top+PH}" stroke="${c.ink2}" stroke-dasharray="5 4"/>`;
  const right=ch.i>NY-8;s+=T(right?x-4:x+4,top-8-lev*16,right?`${Y[ch.i]}: ${ch.label} →`:`→ ${Y[ch.i]}: ${ch.label}`,{size:11.5,fill:c.ink2,anchor:right?'end':'start'})});
 // share line (no text labels on lines, by project convention)
 let d='',pen=false;for(let i=0;i<NY;i++){const v=o.share[i];if(v==null){pen=false;continue}d+=(pen?'L':'M')+xc(i).toFixed(1)+' '+ys(v).toFixed(1);pen=true}
 s+=`<path d="${d}" fill="none" stroke="${c.share}" stroke-width="2.5"/>`;
 for(let i=0;i<NY;i++){const v=o.share[i];if(v!=null)s+=`<circle cx="${xc(i).toFixed(1)}" cy="${ys(v).toFixed(1)}" r="4.5" fill="${c.share}" stroke="${c.surf}" stroke-width="1.5"/>`}
 // footnotes
 let fy=top+PH+xlabH+16;foot.forEach(l=>{s+=T(L-15,fy,l,{size:11,fill:c.ink2});fy+=16});
 // hover targets
 for(let i=0;i<NY;i++)s+=`<rect class="hov" data-i="${i}" x="${(L+bw*i).toFixed(1)}" y="${top}" width="${bw.toFixed(1)}" height="${PH}" fill="transparent"/>`;
 return s+'</svg>';
}

/* ---------- multi-line comparison chart ---------- */
function compareChart(o){
 // o: {title, subtitle, series:[{label,color,vals,dashed,bold}], foot}
 const c=C(),W=1200,L=90,R=1160,top=150,PH=400,H=top+PH+70+30;
 const bw=(R-L)/NY,xc=i=>L+bw*(i+0.5),ys=v=>top+PH-v/105*PH;
 let s=svgEl(W,H)+`<rect width="${W}" height="${H}" fill="${c.surf}"/>`;
 s+=T(L-15,36,o.title,{size:20,bold:1,fill:c.ink})+T(L-15,62,o.subtitle,{size:13.5,fill:c.ink2});
 let lx=L-15;o.series.forEach(se=>{s+=`<line x1="${lx}" y1="${96}" x2="${lx+24}" y2="${96}" stroke="${se.color}" stroke-width="${se.bold?3.2:2.5}" ${se.dashed?'stroke-dasharray="7 3"':''}/><circle cx="${lx+12}" cy="96" r="3.5" fill="${se.color}" stroke="${c.surf}"/>`;
  s+=T(lx+32,100,se.label,{size:13,fill:c.ink});lx+=48+se.label.length*7.2});
 for(let p=0;p<=100;p+=20){const y=ys(p);s+=`<line x1="${L}" x2="${R}" y1="${y}" y2="${y}" stroke="${c.grid}"/>`+T(L-8,y+4,p+'%',{size:12,fill:c.ink2,anchor:'end'})}
 s+=`<line x1="${L}" x2="${L}" y1="${top}" y2="${top+PH}" stroke="${c.ink2}"/><line x1="${L}" x2="${R}" y1="${top+PH}" y2="${top+PH}" stroke="${c.ink2}"/>`;
 s+=T(28,top+PH/2,'City share of county population',{size:13,fill:c.ink2,anchor:'middle',rot:-90});
 for(let i=0;i<NY;i++)s+=T(xc(i)+4,top+PH+16,String(Y[i]),{size:12,fill:c.ink2,anchor:'end',rot:-45});
 o.series.slice().reverse().forEach(se=>{let d='',pen=false;for(let i=0;i<NY;i++){const v=se.vals[i];if(v==null){pen=false;continue}d+=(pen?'L':'M')+xc(i).toFixed(1)+' '+ys(v).toFixed(1);pen=true}
  s+=`<path d="${d}" fill="none" stroke="${se.color}" stroke-width="${se.bold?3.2:2.4}" ${se.dashed?'stroke-dasharray="8 4"':''}/>`;
  for(let i=0;i<NY;i++){const v=se.vals[i];if(v!=null)s+=`<circle cx="${xc(i).toFixed(1)}" cy="${ys(v).toFixed(1)}" r="3.6" fill="${se.color}" stroke="${c.surf}" stroke-width="1.2"/>`}});
 s+=T(L-15,H-14,o.foot,{size:11,fill:c.ink2});
 for(let i=0;i<NY;i++)s+=`<rect class="hov" data-i="${i}" x="${(L+bw*i).toFixed(1)}" y="${top}" width="${bw.toFixed(1)}" height="${PH}" fill="transparent"/>`;
 return s+'</svg>';
}

/* ---------- hover tooltips, downloads ---------- */
function mount(box,svg,tip){box.innerHTML=svg+'<div class="tip"></div>';const t=box.querySelector('.tip'),sv=box.querySelector('svg');
 let band=null;
 sv.querySelectorAll('.hov').forEach(r=>{r.addEventListener('mousemove',e=>{const i=+r.dataset.i;t.innerHTML=tip(i);t.style.display='block';
   const bb=box.getBoundingClientRect();let x=e.clientX-bb.left+14,y=e.clientY-bb.top+10;if(x+t.offsetWidth>bb.width)x=e.clientX-bb.left-t.offsetWidth-14;t.style.left=x+'px';t.style.top=y+'px';
   if(band)band.setAttribute('fill','transparent');band=r;r.setAttribute('fill','rgba(127,127,127,0.10)')});
  r.addEventListener('mouseleave',()=>{t.style.display='none';r.setAttribute('fill','transparent')})})}
function saveBlob(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove()},500)}
function svgString(box){const sv=box.querySelector('svg').cloneNode(true);sv.querySelectorAll('.hov').forEach(n=>n.remove());return new XMLSerializer().serializeToString(sv)}
function dlSvg(box,name){saveBlob(new Blob([svgString(box)],{type:'image/svg+xml'}),name+'.svg')}
function dlPng(box,name){const str=svgString(box),vb=box.querySelector('svg').viewBox.baseVal,sc=2;
 const img=new Image();img.onload=()=>{const cv=document.createElement('canvas');cv.width=vb.width*sc;cv.height=vb.height*sc;const ctx=cv.getContext('2d');ctx.drawImage(img,0,0,cv.width,cv.height);
  cv.toBlob(b=>saveBlob(b,name+'.png'),'image/png')};img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(str)}
function csv(rows){const cols=Object.keys(rows[0]);const q=v=>v==null?'':(/[",\n]/.test(String(v))?'"'+String(v).replace(/"/g,'""')+'"':String(v));
 return [cols.join(',')].concat(rows.map(r=>cols.map(k=>q(r[k])).join(','))).join('\n')}
function dlCsv(rows,name){saveBlob(new Blob([csv(rows)],{type:'text/csv'}),name)}

/* ---------- city views ---------- */
function cityChanges(o){const ch=[];for(let i=1;i<NY;i++){if(o.lab[i]!==o.lab[i-1]&&o.lab[i-1]>=0)ch.push({i,label:st(o.lab[i])})}return ch}
function cityChart(id,log){const c=CITY[id],o=DATA.obs[id];
 return barShareChart({title:`${c.city}, ${c.state}: city vs. county population, 1800–2020`,
  subtitle:`#${c.rank} city in the contiguous U.S. by 2020 Census population (${fmt(c.pop2020)}).  Comparison county (2020): ${c.county2020}.`,
  legend:['City-limits population','County population','City share of county population (right axis)'],
  city:o.c,county:o.k,share:o.s,log,xlab:i=>[String(Y[i])],changes:cityChanges(o),foot:c.foot})}
function cityTip(id){const o=DATA.obs[id];return i=>`<b>${Y[i]}</b><div class="r"><span><span class="sw" style="background:var(--city)"></span>City</span><span>${fmt(o.c[i])}</span></div>
 <div class="r"><span><span class="sw" style="background:var(--county)"></span>County</span><span>${fmt(o.k[i])}</span></div>
 <div class="r"><span><span class="sw" style="background:var(--share)"></span>Share</span><span>${o.s[i]==null?'—':o.s[i].toFixed(1)+'%'}</span></div><div class="meta" style="margin-top:4px">${esc(st(o.lab[i]))}</div>`}
function thumb(id){const o=DATA.obs[id],c=C(),W=300,H=140,L=6,R=294,top=8,PH=124,bw=(R-L)/NY;
 const mx=Math.max(1,...o.k.filter(v=>v!=null),...o.c.filter(v=>v!=null));let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"><rect width="${W}" height="${H}" fill="${c.surf}"/>`;
 for(let i=0;i<NY;i++){[[o.c[i],0,c.city],[o.k[i],1,c.county]].forEach(([v,k,col])=>{if(v==null)return;const h=v/mx*PH;s+=`<rect x="${(L+bw*i+bw*0.12+k*bw*0.38).toFixed(1)}" y="${(top+PH-h).toFixed(1)}" width="${(bw*0.38).toFixed(1)}" height="${h.toFixed(1)}" fill="${col}"/>`})}
 let d='',pen=false;for(let i=0;i<NY;i++){const v=o.s[i];if(v==null){pen=false;continue}d+=(pen?'L':'M')+(L+bw*(i+0.5)).toFixed(1)+' '+(top+PH-v/105*PH).toFixed(1);pen=true}
 return s+`<path d="${d}" fill="none" stroke="${c.share}" stroke-width="2"/></svg>`}
function renderGrid(){const q=$('#q').value.trim().toLowerCase(),stv=$('#state').value,so=$('#sort').value,mn=$('#smin').value,mxv=$('#smax').value;
 let r=DATA.cities.filter(c=>(!q||q.split(/\s+/).every(t=>c.search.includes(t)))&&(!stv||c.state===stv)&&(mn===''||c.share2020>=+mn)&&(mxv===''||c.share2020<=+mxv));
 const sorts={rank:(a,b)=>a.rank-b.rank,name:(a,b)=>a.city.localeCompare(b.city),share:(a,b)=>a.share2020-b.share2020,share_desc:(a,b)=>b.share2020-a.share2020,peak:(a,b)=>b.peak-a.peak,area:(a,b)=>b.area-a.area};
 r.sort(sorts[so]);$('#count').textContent=`${r.length} of ${DATA.cities.length} cities`;
 $('#grid').innerHTML=r.map(c=>`<div class="card" data-id="${c.id}">${thumb(c.id)}<div class="m"><b>#${c.rank} ${esc(c.city)}, ${c.state}</b>
  <div class="meta">${fmt(c.pop2020)} (2020) · ${esc(c.county2020)}</div><div class="meta"><span class="pill">2020 share ${c.share2020.toFixed(1)}%</span><span class="pill">peak ${c.peak.toFixed(0)}% (${c.peakYear})</span><span class="pill">${c.area} sq mi</span></div></div></div>`).join('');
 document.querySelectorAll('.card').forEach(e=>e.onclick=()=>{location.hash=e.dataset.id})}
let curCity=null,curLog=false;
function renderDetail(id){const c=CITY[id];if(!c){location.hash='';return}const o=DATA.obs[id];curCity=id;
 $('#detail').innerHTML=`<p><a href="#">← All cities</a></p><h2>#${c.rank} ${esc(c.city)}, ${esc(c.stateName)}</h2>
 <p class="meta">2020 population ${fmt(c.pop2020)} · comparison county: ${esc(c.county2020)} · 2020 share ${c.share2020.toFixed(1)}% · peak share ${c.peak.toFixed(1)}% in ${c.peakYear} · ${c.region} · 2020 land area ${c.area} sq mi (${c.quartile})</p>
 <div class="ctl"><span class="seg"><button id="lin">Linear scale</button><button id="lg">Log scale</button></span>
 <span class="meta"><a class="btn" id="cPng">Download PNG</a> · <a class="btn" id="cSvg">SVG</a> · <a class="btn" id="cCsv">Data (CSV)</a></span></div>
 <div class="chartbox" id="cityBox"></div>
 <div class="tw"><table><thead><tr><th>Year</th><th>City pop.</th><th>County pop.</th><th>Share %</th><th class="l">Comparison county</th><th class="l">Basis</th><th class="l">City source</th><th class="l">County source</th></tr></thead><tbody>
 ${Y.map((y,i)=>`<tr><td>${y}</td><td>${fmt(o.c[i])}</td><td>${fmt(o.k[i])}</td><td>${o.s[i]==null?'—':o.s[i].toFixed(1)}</td><td class="l">${esc(st(o.lab[i]))}</td><td class="l">${esc(st(o.basis[i]))}</td><td class="l">${esc(st(o.csrc[i]))}</td><td class="l">${esc(st(o.ksrc[i]))}</td></tr>`).join('')}</tbody></table></div>`;
 const draw=()=>{mount($('#cityBox'),cityChart(id,curLog),cityTip(id));$('#lin').className=curLog?'':'on';$('#lg').className=curLog?'on':''};
 $('#lin').onclick=()=>{curLog=false;draw()};$('#lg').onclick=()=>{curLog=true;draw()};
 $('#cPng').onclick=()=>dlPng($('#cityBox'),id+(curLog?'_log':''));$('#cSvg').onclick=()=>dlSvg($('#cityBox'),id+(curLog?'_log':''));
 $('#cCsv').onclick=()=>dlCsv(panelRows(id),id+'.csv');draw();window.scrollTo(0,0)}
function panelRows(only){const rows=[];DATA.cities.forEach(c=>{if(only&&c.id!==only)return;const o=DATA.obs[c.id];Y.forEach((y,i)=>rows.push({city_id:c.id,rank:c.rank,city:c.city,state:c.state,year:y,
 city_pop:o.c[i],county_pop:o.k[i],share_pct:o.s[i],county_label:st(o.lab[i]),county_keys:st(o.keys[i]),county_basis:st(o.basis[i]),county_note:st(o.note[i]),city_source:st(o.csrc[i]),county_source:st(o.ksrc[i])}))});return rows}

/* ---------- averages / city size ---------- */
const SCH={region:{title:'National and regional averages',intro:'Averages across the top-100 cities, nationally and by U.S. Census region.',seg:'Region',
  cmp:'Average share of county population: national and the four regions'},
 size:{title:'City size: averages by land-area quartile',intro:"Averages across the top-100 cities grouped into quartiles of 2020 land area (25 cities each). Quartiles use 2020 boundaries for every year, so they group cities by today's size, not their size at the time.",seg:'Land area',
  cmp:'Average share of county population: all cities and the four land-area quartiles'}};
const COLVAR={National:'--g-national',Northeast:'--g-northeast',Midwest:'--g-midwest',South:'--g-south',West:'--g-west',Q1:'--q1',Q2:'--q2',Q3:'--q3',Q4:'--q4'};
let aS='region',aG='National',aW='unweighted';
function groupColor(s,g){return css(s==='size'&&g==='National'?'--g-all':COLVAR[g])}
function renderAvg(){const S=DATA.schemes[aS],M=SCH[aS],ser=S.series[aG][aW],wl=DATA.weightings[aW];
 $('#aggTitle').textContent=M.title;$('#aggIntro').textContent=M.intro;$('#segLabel').textContent=M.seg;$('#cmpTitle').textContent=M.cmp;
 $('#segGroup').innerHTML=S.groups.map(g=>`<button data-g="${g}" class="${g===aG?'on':''}">${esc(S.button[g])}</button>`).join('');
 document.querySelectorAll('#segGroup button').forEach(b=>b.onclick=()=>{aG=b.dataset.g;renderAvg()});
 document.querySelectorAll('#segW button').forEach(b=>{b.className=b.dataset.w===aW?'on':'';b.onclick=()=>{aW=b.dataset.w;renderAvg()}});
 const sub=aW==='unweighted'?'Line: simple mean of city shares.':'Line: total city pop. ÷ total county pop. (ratio of the bars).';
 const svg=barShareChart({title:`${S.title[aG]}: city vs. county population, 1800–2020 (${wl.toLowerCase()})`,
  subtitle:`Top-100 contiguous-U.S. cities (2020), ${S.scope[aG]}. ${sub}`,
  legend:['Mean city-limits population','Mean county population',(aW==='unweighted'?'Mean city share of county population':'Population-weighted city share of county population')+' (right axis)'],
  city:ser.mc,county:ser.mk,share:ser.s,log:false,twoLine:true,xlab:i=>[String(Y[i]),'n='+(ser.n[i]||0)],changes:[],foot:S.foot[aG][aW],yTitle:'Population (mean across cities)'});
 mount($('#aggBox'),svg,i=>`<b>${Y[i]}</b> <span class="meta">n=${ser.n[i]||0}</span><div class="r"><span><span class="sw" style="background:var(--city)"></span>Mean city</span><span>${fmt(ser.mc[i])}</span></div>
  <div class="r"><span><span class="sw" style="background:var(--county)"></span>Mean county</span><span>${fmt(ser.mk[i])}</span></div><div class="r"><span><span class="sw" style="background:var(--share)"></span>Share</span><span>${ser.s[i]==null?'—':ser.s[i].toFixed(1)+'%'}</span></div>`);
 const series=S.groups.map(g=>({g,label:S.legend[g],color:groupColor(aS,g),vals:S.series[g][aW].s,bold:g==='National',dashed:S.dashedAll&&g==='National'}));
 const csub=aW==='unweighted'?'Simple mean of city shares':'Shares weighted by county population (total city ÷ total county pop.)';
 mount($('#cmpBox'),compareChart({title:`Average city share of county population: ${S.compareTitle} (${wl.toLowerCase()})`,
  subtitle:`Top 100 contiguous-U.S. cities (2020). ${csub}; each year uses cities with both counts.`,series,
  foot:'Early years rest on few cities per group (see the n counts in the group chart).'+(aS==='size'?' Quartiles use 2020 land area for every year.':'')+' Sources: decennial census counts.'}),
  i=>`<b>${Y[i]}</b>`+series.map(se=>`<div class="r"><span><span class="sw" style="background:${se.color}"></span>${esc(se.label)}</span><span>${se.vals[i]==null?'—':se.vals[i].toFixed(1)+'%'}</span></div>`).join(''));
 const name=`${aS==='size'?'size':'agg'}_${aG.toLowerCase()}_${aW}`;
 $('#aggPng').onclick=()=>dlPng($('#aggBox'),name);$('#aggSvg').onclick=()=>dlSvg($('#aggBox'),name);
 $('#cmpPng').onclick=()=>dlPng($('#cmpBox'),`${aS==='size'?'size_compare':'compare'}_${aW}`);$('#cmpSvg').onclick=()=>dlSvg($('#cmpBox'),`${aS==='size'?'size_compare':'compare'}_${aW}`);
 $('#aggCsv').onclick=()=>dlCsv(Y.map((y,i)=>({scheme:aS,group:aG,weighting:aW,year:y,n_cities:ser.n[i],mean_city_pop:ser.mc[i],mean_county_pop:ser.mk[i],share_pct:ser.s[i]})),`averages_${aS}_${aG.toLowerCase()}_${aW}.csv`);
 $('#aggMembers').textContent=`${aG==='National'?'All':S.button[aG]} cities (${S.members[aG].length}): ${S.members[aG].join(', ')}.`;
 $('#aggRows').innerHTML=Y.map((y,i)=>`<tr><td>${y}</td><td>${ser.n[i]||0}</td><td>${fmt(ser.mc[i])}</td><td>${fmt(ser.mk[i])}</td><td>${ser.s[i]==null?'—':ser.s[i].toFixed(1)}</td></tr>`).join('')}
function aggRowsAll(){const rows=[];for(const [sk,S] of Object.entries(DATA.schemes))S.groups.forEach(g=>Object.keys(DATA.weightings).forEach(w=>{const z=S.series[g][w];
 Y.forEach((y,i)=>rows.push({scheme:sk,group:g,weighting:w,year:y,n_cities:z.n[i],mean_city_pop:z.mc[i],mean_county_pop:z.mk[i],share_pct:z.s[i]}))}));return rows}

/* ---------- routing ---------- */
function show(id){['browse','detail','averages','data'].forEach(k=>$('#'+k).style.display=k===id?'block':'none');
 $('#tBrowse').className=(id==='browse'||id==='detail')?'on':'';$('#tAvg').className=id==='averages'&&aS==='region'?'on':'';$('#tSize').className=id==='averages'&&aS==='size'?'on':'';$('#tData').className=id==='data'?'on':'';
 $('#filters').style.display=id==='browse'?'contents':'none'}
function route(){const h=decodeURIComponent(location.hash.slice(1));
 if(h==='averages'||h==='citysize'){const k=h==='citysize'?'size':'region';if(k!==aS){aS=k;aG='National'}show('averages');renderAvg();return}
 if(h==='data'){show('data');return}
 if(h){show('detail');renderDetail(h)}else{show('browse');renderGrid()}}
[...new Set(DATA.cities.map(c=>c.state))].map(s=>[s,DATA.cities.find(c=>c.state===s).stateName]).sort((a,b)=>a[1].localeCompare(b[1])).forEach(([s,n])=>$('#state').insertAdjacentHTML('beforeend',`<option value="${s}">${esc(n)}</option>`));
let tm;['#q','#smin','#smax'].forEach(s=>$(s).oninput=()=>{clearTimeout(tm);tm=setTimeout(renderGrid,120)});['#state','#sort'].forEach(s=>$(s).onchange=renderGrid);
$('#tBrowse').onclick=()=>{location.hash=''};$('#tAvg').onclick=()=>{location.hash='averages'};$('#tSize').onclick=()=>{location.hash='citysize'};$('#tData').onclick=()=>{location.hash='data'};
$('#dlPanel').onclick=()=>dlCsv(panelRows(),'city_county_panel.csv');
$('#dlCities').onclick=()=>dlCsv(DATA.cities.map(c=>({rank:c.rank,city_id:c.id,city:c.city,state:c.state,region:c.region,pop_2020:c.pop2020,county_2020:c.county2020,share_2020:c.share2020,peak_share:c.peak,peak_share_year:c.peakYear,land_area_sqmi_2020:c.area,size_quartile:c.quartile,notes:c.notes})),'cities.csv');
$('#dlAgg').onclick=()=>dlCsv(aggRowsAll(),'averages.csv');
$('#foot').textContent=`Data built ${DATA.generated} from decennial census counts. Single-file version of the city_pop project; works offline.`;
window.onhashchange=route;
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',route);
route();
</script></body></html>"""


if __name__ == "__main__":
    main()
