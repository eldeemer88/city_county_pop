# City vs. county population, 1800–2020 (top 100 cities in the contiguous U.S., 2020 Census)

**Live app:** https://eldeemer88.github.io/city_county_pop/ (single file: [`docs/index.html`](docs/index.html))

For each of the 100 most populous incorporated places in the contiguous United States in the 2020 Census
(Honolulu and Anchorage excluded, so ranks 55+ differ from national ranks by one or two), this project
draws a chart of decennial census counts, 1800–2020, showing:

* **blue bar**: population inside city limits;
* **light bar** beside it: population of the county (or county-equivalent) containing the city at that census;
* **orange line** (right axis, fixed 0–100%): the city's share of that county's population.

Dashed vertical rules mark censuses where the comparison county changes (e.g. Denver: Arapahoe County → City and County of Denver, 1902).
Every chart is produced in a linear and a log population scale, and everything is loaded into a
searchable SQLite database with a local browser tool.

## Quick start

**Just look at it:** open `docs/index.html` in any browser. It is a single self-contained file
(about 0.3 MB) with all the data embedded and the charts drawn in the browser, so it works offline
with nothing installed and can be emailed, shared or posted as is. It has the city charts
(linear/log), the Averages and City Size views, hover values, and PNG/SVG/CSV downloads.

**Rebuild everything from the raw data:**

```bash
pip install -r requirements.txt     # pandas, matplotlib
python run_all.py                    # sources → panel → graphs → averages → database → docs/index.html
```

**Local search tool with SQL:** `python app/serve.py` opens http://127.0.0.1:8765. It uses only
the Python standard library and opens `output/city_pop.db` read-only. Compared with the single-file
version, it adds a read-only SQL tab and serves the matplotlib PNGs and PDFs.

You can also query the database directly:

```bash
sqlite3 output/city_pop.db "SELECT city, share_2020, peak_share, peak_share_year FROM cities ORDER BY share_2020;"
sqlite3 output/city_pop.db "SELECT city, year, share_pct FROM observations WHERE year=1950 ORDER BY share_pct DESC;"
```

## National and regional averages

`src/make_aggregates.py` averages the panel nationally and by U.S. Census region (Northeast 7 cities,
Midwest 17, South 39, West 37; assigned by state). For each group and census year the sample is
the cities with **both** a city and a county count that year (the *n* printed under each year), so
early years rest on few cities and the sample grows over time.

* **Bars:** mean city-limits population and mean county population across those cities.
* **Unweighted line:** simple mean of the city shares, so each city counts equally.
* **Population-weighted line:** shares weighted by county population, i.e. total city population ÷ total county population (exactly the ratio of the two bars).
* Counties containing several of the cities (e.g. Maricopa, Los Angeles, Dallas, Clark) count once per city. New York (five boroughs, share 100%) dominates the Northeast's weighted average.

Outputs: `data/processed/aggregates.csv` (rows with `scheme = 'region'`), `output/graphs/aggregates/*.png` (10 group charts plus
2 comparison charts) and `output/graphs/averages.pdf` (one chart per page). In the app, the
**Averages** tab shows a single chart with region and weighting selectors, and below it the
comparison of average shares for the nation and the four regions (following the selected weighting).
Database tables: `aggregates`, `city_regions`, `agg_graphs`.

## City size (land-area quartiles)

The same averages are computed for quartiles of **2020 land area** (U.S. Census Bureau 2020
Gazetteer, via Wikipedia; `config/city_land_area.csv`): 25 cities each, ties broken by population rank.

| Quartile | 2020 land area |
|---|---|
| Q1 (smallest) | 14.7–65.3 sq mi |
| Q2 | 65.6–110.6 sq mi |
| Q3 | 110.7–195.4 sq mi |
| Q4 (largest) | 197.5–747.3 sq mi |

Quartiles use 2020 boundaries for every year, so they group cities by today's size, not their size
at the time; many cities reached their current area through annexation. Definitions of the bars and
the unweighted / population-weighted lines are the same as above. Outputs:
`output/graphs/aggregates/size_*.png`, `output/graphs/city_size.pdf`, the **City Size** tab in
the app, and database tables `city_size` and `aggregates` (rows with `scheme = 'size'`).

## Layout

```
config/cities.csv            top-100 list (contiguous-U.S. rank), 2020 Census counts, city notes (shown as chart footnotes)
config/county_map.csv        which county (or counties) is the comparator for each city and year range
config/city_land_area.csv    2020 land area per city (for the City Size quartiles)
config/city_overrides.csv    documented manual corrections to source city values (currently one: Madison 1840)
data/raw/                    source files (two pinned GitHub downloads + one transcription)
data/processed/panel.csv     city × year panel (the data behind every chart)
data/processed/validation_county_overlap.csv   transcription check (see below)
src/fetch_sources.py         download & SHA-256-verify the pinned sources (falls back to cached copies)
src/build_panel.py           assemble the panel
src/make_graphs.py           draw the charts (matplotlib)
src/make_aggregates.py       national / Census-region averages and their charts
src/build_db.py              build output/city_pop.db
src/export_static.py         build docs/index.html (single-file web app)
docs/index.html              the single-file web app (also the GitHub Pages site)
app/serve.py                 local search tool
output/graphs/               NN_city.png, NN_city_log.png, all_cities.pdf, all_cities_log.pdf, averages.pdf, aggregates/
output/city_pop.db           SQLite: cities, observations, graphs (PNG blobs), sources, city_search (FTS5)
```

## Data sources (all decennial census counts)

| Series | Years | Source |
|---|---|---|
| City population | 1800–2010 | Steiner & Heppler, *United States Historical City Populations, 1790–2010* (Stanford CESTA), compiled mainly from U.S. Census Bureau counts of places. Pinned commit `9b267ba`. |
| City population | 2020 | 2020 Census (P.L. 94-171) counts of incorporated places, stored in `config/cities.csv`. |
| County population | 1900–2020 | Van Leuven, *Historical U.S. County Population Data* (Census Bureau "Population of Counties by Decennial Census: 1900 to 1990" + 2000–2020 counts; doi:10.7910/DVN/WLS5GF). Pinned commit `51b9704`. |
| County population | 1790–1890, plus defunct Princess Anne Co., VA | Forstall (1996), *Population of States and Counties of the United States: 1790–1990* (U.S. Census Bureau), as tabulated in Wikipedia county articles. Transcribed on 2026-10-14 into `data/raw/county_wikipedia_transcribed.csv`, one source URL per row. |

**Transcription check.** The transcription also covers 1900–2020, so it can be compared with the
Census county file: of 988 overlapping county-years, 980 match exactly and 8 differ by ≤0.38%
(post-census count revisions, e.g. Los Angeles and Maricopa 1970, Essex and Hudson 1970).
Exception: Orleans Parish's Wikipedia table is empty, so its 1820–1870 counts come from the
parish figures quoted in the *New Orleans* article; 1810 is left blank. See
`data/processed/validation_county_overlap.csv`. This is the one input that is a transcription rather
than a scripted download; NHGIS (`ts_nominal_county`) or Forstall's original tables would be a
direct-download alternative if you want to replace it.

## Definitions and judgment calls

* **Comparison county** = the county (or county-equivalent) containing the city's core *as it existed at each census*. County figures are as reported, so they reflect historical boundaries.
* **Cities spanning several counties** (e.g. Houston, Dallas, Fort Worth, Austin, Columbus, Kansas City, Oklahoma City, Atlanta, Tulsa, Aurora, Plano, Corpus Christi; see `extends_beyond_principal_county`) are compared with their principal county. Because the city numerator includes residents outside that county, the share is somewhat overstated. The chart footnote says so, and `cities.extends_beyond_principal_county = 'yes'`.
* **Time-varying comparators** (`config/county_map.csv`):
  * New York: pre-1898, the City of New York and New York County shared boundaries (county = city); from 1900, the sum of the five borough counties.
  * San Francisco: coterminous from 1856; the 1850 returns were lost in a fire.
  * Baltimore: Baltimore County (which includes the city) through 1850; Baltimore City (independent since 1851) after that.
  * Denver: Arapahoe County through 1900; Denver County from 1910.
  * Atlanta: DeKalb County in 1850; Fulton County from 1860.
  * Portland: Washington County in 1850; Multnomah County from 1860.
  * Virginia Beach: Princess Anne County through 1950; Princess Anne County + Virginia Beach city in 1960; Virginia Beach city from 1970.
  * Richmond and Norfolk, VA: the census county tables include these independent cities within Henrico and Norfolk counties through 1890; from 1900 the comparator is the independent city itself. Chesapeake uses its predecessor, Norfolk County, through 1960.
  * St. Louis: St. Louis County (including the city) through 1870; the independent city from 1880.
  * New Orleans: Orleans Parish; the city has covered the whole parish since 1874.
  * Anaheim, Santa Ana and Irvine: Los Angeles County through 1880, then Orange County. Riverside: San Bernardino County in 1890. Buffalo: Niagara County in 1810–1820. St. Petersburg: Hillsborough County through 1910, then Pinellas.
* **Consolidated city-counties** show shares at or near 100% after consolidation: Philadelphia 1854, San Francisco, Denver, D.C., Baltimore, New York, Virginia Beach. Nashville (1963), Indianapolis (1970), Jacksonville (1968) and Louisville (2003) show jumps; post-merger figures are the consolidated "balance" (Nashville 1970 is the full consolidated total in the source).
* **D.C. county-equivalent** figures cover present-day D.C. (they exclude Alexandria before 1846).
* **Manual correction.** Madison's 1840 city value (1,500, a Populstat estimate) exceeds the census count for all of Dane County (314), so it is set to missing in `config/city_overrides.csv`.
* **Missing values.** CESTA records places below the Census reporting threshold (2,500 before 1950) as 0; these are treated as missing, so early bars may be absent even where a settlement existed. A few pre-threshold values come from state data centers or Populstat (see `observations.city_source`).
* **Shares slightly above 100%** (≤0.1%, e.g. Denver 1980) come from small differences between original and revised counts in the two sources; they are left as reported.
* **Dual axis.** The share axis is fixed at 0–100%, so the line's height is never stretched to match the bars.

## Chart conventions

Line series carry no text labels on the lines themselves (no end-of-line or value labels); the legend
identifies each series. Keep this for any new line charts.

## Reproducibility

`run_all.py` is deterministic. Remote inputs are pinned to commit hashes and verified by SHA-256.
If you are offline, the cached copies in `data/raw/` are verified and used instead. To change the
city set or a comparator, edit the two files in `config/` and re-run.
