"""Step 4: load the panel, metadata, sources and graphs into a SQLite database.

output/city_pop.db
  cities        one row per city (rank, 2020 population, notes, current county)
  observations  city x census year panel (populations, share, sources)
  graphs        PNG images (linear and log scale) stored as BLOBs
  sources       citations, URLs and SHA-256 hashes of the input files
  city_search   FTS5 full-text index over names, states, counties and notes

Query it with any SQLite client, e.g.
  sqlite3 output/city_pop.db "SELECT city, year, share_pct FROM observations WHERE city='Detroit';"
or browse it with the local app:  python app/serve.py
"""
import hashlib
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from config import CONFIG, DB_PATH, GRAPHS, PROCESSED, SOURCES, WIKI_COUNTY_FILE

STATE_NAMES = {
    "AZ": "Arizona", "ID": "Idaho", "LA": "Louisiana", "NJ": "New Jersey", "CA": "California", "CO": "Colorado", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "IL": "Illinois", "IN": "Indiana", "KS": "Kansas",
    "KY": "Kentucky", "MA": "Massachusetts", "MD": "Maryland", "MI": "Michigan",
    "MN": "Minnesota", "MO": "Missouri", "NC": "North Carolina", "NE": "Nebraska",
    "NM": "New Mexico", "NV": "Nevada", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "TN": "Tennessee", "TX": "Texas", "VA": "Virginia",
    "WA": "Washington", "WI": "Wisconsin",
}

SCHEMA = """
CREATE TABLE cities (
  city_id TEXT PRIMARY KEY, rank INTEGER, city TEXT, state TEXT, state_name TEXT,
  pop_2020 INTEGER, county_2020 TEXT, share_2020 REAL, peak_share REAL, peak_share_year INTEGER,
  extends_beyond_principal_county TEXT, city_notes TEXT);
CREATE TABLE observations (
  city_id TEXT REFERENCES cities(city_id), rank INTEGER, city TEXT, state TEXT, year INTEGER,
  city_pop INTEGER, county_pop INTEGER, share_pct REAL, county_label TEXT, county_keys TEXT,
  county_basis TEXT, county_note TEXT, city_source TEXT, county_source TEXT,
  PRIMARY KEY (city_id, year));
CREATE TABLE graphs (
  city_id TEXT REFERENCES cities(city_id), scale TEXT, filename TEXT, png BLOB,
  PRIMARY KEY (city_id, scale));
CREATE TABLE sources (key TEXT PRIMARY KEY, file TEXT, url TEXT, sha256 TEXT, citation TEXT);
CREATE TABLE search_index (city_id TEXT, city TEXT, state TEXT, counties TEXT, notes TEXT);
CREATE TABLE city_regions (city_id TEXT PRIMARY KEY REFERENCES cities(city_id), region TEXT);
CREATE TABLE city_size (city_id TEXT PRIMARY KEY REFERENCES cities(city_id),
  land_area_sqmi_2020 REAL, size_quartile TEXT, source TEXT);
CREATE TABLE aggregates (
  scheme TEXT, "group" TEXT, weighting TEXT, year INTEGER, n_cities INTEGER, n_group INTEGER,
  mean_city_pop INTEGER, mean_county_pop INTEGER, share_pct REAL,
  PRIMARY KEY (scheme, "group", weighting, year));
CREATE TABLE agg_graphs (name TEXT PRIMARY KEY, filename TEXT, png BLOB);
"""
# Optional full-text index; some Python builds ship SQLite without FTS5, in which
# case the app falls back to plain LIKE matching on search_index.
FTS = """CREATE VIRTUAL TABLE city_search USING fts5(city_id UNINDEXED, city, state, counties, notes,
  tokenize = 'unicode61 remove_diacritics 2');"""


def build():
    # Build in the OS temp dir, then copy into place: robust on network/synced folders
    # where SQLite's journal locking can fail, and never leaves a half-written database.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmpdir = tempfile.mkdtemp()
    tmp_db = Path(tmpdir) / DB_PATH.name
    _build(tmp_db)
    for stale in [DB_PATH.with_name(DB_PATH.name + s) for s in ("-journal", "-wal", "-shm")]:
        if stale.exists():
            stale.unlink()
    shutil.copyfile(tmp_db, DB_PATH)
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"[db] wrote {DB_PATH}")


def _build(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    try:
        con.executescript(FTS)
        has_fts = True
    except sqlite3.OperationalError:
        has_fts = False
        print("[db] SQLite FTS5 not available; using plain search index only")

    panel = pd.read_csv(PROCESSED / "panel.csv")
    cities = pd.read_csv(CONFIG / "cities.csv")

    for c in cities.itertuples():
        p = panel[panel.city_id == c.city_id].sort_values("year")
        last = p[p.year == 2020].iloc[0]
        valid = p.dropna(subset=["share_pct"])
        peak = valid.loc[valid.share_pct.idxmax()] if len(valid) else None
        con.execute("INSERT INTO cities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            c.city_id, int(c.rank), c.city, c.state, STATE_NAMES[c.state], int(c.pop_2020),
            last.county_label, float(last.share_pct),
            float(peak.share_pct) if peak is not None else None,
            int(peak.year) if peak is not None else None,
            c.extends_beyond_principal_county, c.city_notes if isinstance(c.city_notes, str) else ""))
        notes = " ".join([c.city_notes if isinstance(c.city_notes, str) else ""] +
                         [n for n in p.county_note.dropna().unique()])
        search_row = (c.city_id, c.city, f"{c.state} {STATE_NAMES[c.state]}",
                      " ".join(p.county_label.dropna().unique()), notes)
        con.execute("INSERT INTO search_index VALUES (?,?,?,?,?)", search_row)
        if has_fts:
            con.execute("INSERT INTO city_search VALUES (?,?,?,?,?)", search_row)
        for scale, suffix in [("linear", ""), ("log", "_log")]:
            f = GRAPHS / f"{int(c.rank):02d}_{c.city_id}{suffix}.png"
            if f.exists():
                con.execute("INSERT INTO graphs VALUES (?,?,?,?)",
                            (c.city_id, scale, f.name, f.read_bytes()))

    obs_cols = ["city_id", "rank", "city", "state", "year", "city_pop", "county_pop", "share_pct",
                "county_label", "county_keys", "county_basis", "county_note", "city_source",
                "county_source"]
    panel = panel[obs_cols].astype(object).where(panel[obs_cols].notna(), None)
    con.executemany(f"INSERT INTO observations VALUES ({','.join('?' * len(obs_cols))})",
                    panel.itertuples(index=False, name=None))

    for key, s in SOURCES.items():
        con.execute("INSERT INTO sources VALUES (?,?,?,?,?)",
                    (key, s["file"].name, s["url"], s["sha256"], s["citation"]))
    con.execute("INSERT INTO sources VALUES (?,?,?,?,?)", (
        "forstall_wikipedia", WIKI_COUNTY_FILE.name, "https://en.wikipedia.org (county articles; "
        "per-row URLs in the file)", hashlib.sha256(WIKI_COUNTY_FILE.read_bytes()).hexdigest(),
        "Forstall, R. L. (1996). Population of States and Counties of the United States: 1790-1990. "
        "U.S. Bureau of the Census. Transcribed from the 'Historical population' tables of Wikipedia "
        "county articles (accessed 2026-10-14); checked against the Census 1900-2020 county file."))
    con.execute("INSERT INTO sources VALUES (?,?,?,?,?)", (
        "census_2020", "config/cities.csv", "https://www.census.gov/programs-surveys/decennial-census/"
        "about/rdo/summary-files.html", None,
        "U.S. Census Bureau, 2020 Census Redistricting Data (P.L. 94-171), total population of "
        "incorporated places."))
    # National / Census-region averages (built by make_aggregates.py)
    from make_aggregates import AGG_DIR, STATE_REGION, size_quartiles
    con.executemany("INSERT INTO city_regions VALUES (?,?)",
                    [(c.city_id, STATE_REGION[c.state]) for c in cities.itertuples()])
    q = size_quartiles()
    con.executemany("INSERT INTO city_size VALUES (?,?,?,?)",
                    [(r.city_id, float(r.land_area_sqmi_2020), r.group, r.source) for r in q.itertuples()])
    agg_file = PROCESSED / "aggregates.csv"
    if agg_file.exists():
        agg = pd.read_csv(agg_file)
        cols = ["scheme", "group", "weighting", "year", "n_cities", "n_group", "mean_city_pop",
                "mean_county_pop", "share_pct"]
        agg = agg[cols].astype(object).where(agg[cols].notna(), None)
        con.executemany("INSERT INTO aggregates VALUES (?,?,?,?,?,?,?,?,?)",
                        agg.itertuples(index=False, name=None))
        for f in sorted(AGG_DIR.glob("*.png")):
            con.execute("INSERT INTO agg_graphs VALUES (?,?,?)", (f.stem, f.name, f.read_bytes()))
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM graphs").fetchone()[0]
    con.close()
    print(f"[db] {len(cities)} cities, {len(panel)} observations, {n} graphs")


if __name__ == "__main__":
    build()
