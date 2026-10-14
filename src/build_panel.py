"""Step 2: build the city-county decennial panel (1800-2020).

Outputs
-------
data/processed/panel.csv          one row per city x census year
data/processed/county_series.csv  every county series used, with its source
data/processed/validation_county_overlap.csv
    Compares the Wikipedia/Forstall transcription with the Census 1900-2020
    county file in years both cover, as a check on the transcription.

Rules
-----
City population: CESTA (1800-2010) matched on 'City, ST'; 2020 from the 2020
    census count in config/cities.csv. CESTA stores "not reported" as 0, so
    zeros are treated as missing.
County population: Census county file (van Leuven) for 1900-2020; the
    Wikipedia transcription of Forstall (1996) for 1800-1890 and for defunct
    counties. Which county (or counties) apply to a city in a given year is set
    in config/county_map.csv:
      county       a single county or county-equivalent
      sum          the sum of several counties (NYC five boroughs; VB 1960)
      coterminous  city and county share the same boundaries, so county = city
"""
import numpy as np
import pandas as pd

from config import CONFIG, PROCESSED, SOURCES, WIKI_COUNTY_FILE, YEARS


def load_cities():
    return pd.read_csv(CONFIG / "cities.csv", dtype={"pop_2020": "Int64"})


def load_cesta():
    df = pd.read_csv(SOURCES["cesta"]["file"], encoding="latin1")
    year_cols = [str(y) for y in range(1790, 2011, 10)]
    long = df.melt(id_vars=["CityST", "Population Source"], value_vars=year_cols,
                   var_name="year", value_name="city_pop")
    long["year"] = long["year"].astype(int)
    long.loc[long["city_pop"] <= 0, "city_pop"] = np.nan
    return long


def load_county_sources():
    """Return a long table: county_key, year, population, source."""
    avl = pd.read_csv(SOURCES["vanleuven"]["file"], dtype={"cty_fips": str})
    avl = avl.melt(id_vars=["cty_fips", "cty"], var_name="col", value_name="population")
    avl["year"] = avl["col"].str[4:].astype(int)
    avl = avl.rename(columns={"cty_fips": "county_key", "cty": "county_name"})
    avl.loc[avl["population"] <= 0, "population"] = np.nan  # county did not exist yet
    avl["source"] = "Census county file 1900-2020 (van Leuven)"

    wiki = pd.read_csv(WIKI_COUNTY_FILE, dtype={"county_key": str})
    wiki["source"] = "Forstall (1996) via Wikipedia transcription"
    return avl[["county_key", "county_name", "year", "population", "source"]], wiki


def county_value(key, year, avl_idx, wiki_idx):
    """Census file first for 1900+; otherwise the Forstall/Wikipedia transcription."""
    if year >= 1900 and (key, year) in avl_idx.index:
        v = avl_idx.loc[(key, year), "population"]
        if pd.notna(v):
            return float(v), avl_idx.loc[(key, year), "source"]
    if (key, year) in wiki_idx.index:
        return float(wiki_idx.loc[(key, year), "population"]), wiki_idx.loc[(key, year), "source"]
    return np.nan, None


def build():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    cities = load_cities()
    cesta = load_cesta()
    cmap = pd.read_csv(CONFIG / "county_map.csv", dtype=str)
    cmap[["start_year", "end_year"]] = cmap[["start_year", "end_year"]].astype(int)
    avl, wiki = load_county_sources()
    avl_idx = avl.set_index(["county_key", "year"]).sort_index()
    wiki_idx = wiki.set_index(["county_key", "year"]).sort_index()

    missing = set(cities["cesta_cityst"]) - set(cesta["CityST"])
    if missing:
        raise SystemExit(f"Cities not found in CESTA: {missing}")

    # Documented manual corrections (config/city_overrides.csv); blank city_pop = missing.
    overrides = pd.read_csv(CONFIG / "city_overrides.csv")
    ov_idx = {(r.city_id, int(r.year)): r for r in overrides.itertuples()}

    rows = []
    for c in cities.itertuples():
        cs = cesta[cesta["CityST"] == c.cesta_cityst].set_index("year")
        for y in YEARS:
            if y == 2020:
                city_pop, city_src = float(c.pop_2020), "2020 Decennial Census (P.L. 94-171)"
            else:
                city_pop = cs.loc[y, "city_pop"] if y in cs.index else np.nan
                city_src = f"CESTA ({cs.loc[y, 'Population Source']})" if pd.notna(city_pop) else None
            if (c.city_id, y) in ov_idx:
                o = ov_idx[(c.city_id, y)]
                city_pop = float(o.city_pop) if pd.notna(o.city_pop) else np.nan
                city_src = f"Override: {o.reason}"

            m = cmap[(cmap.city_id == c.city_id) & (cmap.start_year <= y) & (cmap.end_year >= y)]
            if len(m) != 1:
                raise SystemExit(f"County map for {c.city_id} {y}: {len(m)} rows")
            m = m.iloc[0]
            if m.basis == "coterminous":
                county_pop, county_src = city_pop, "Coterminous with city (county = city)"
            else:
                vals, srcs = [], set()
                for key in m.county_keys.split(";"):
                    v, s = county_value(key, y, avl_idx, wiki_idx)
                    if pd.notna(v):
                        vals.append(v)
                        srcs.add(s)
                county_pop = float(np.sum(vals)) if vals else np.nan
                county_src = "; ".join(sorted(srcs)) if srcs else None

            share = 100 * city_pop / county_pop if pd.notna(city_pop) and pd.notna(county_pop) else np.nan
            rows.append(dict(rank=c.rank, city_id=c.city_id, city=c.city, state=c.state, year=y,
                             city_pop=city_pop, county_pop=county_pop, share_pct=share,
                             county_label=m.county_label, county_keys=m.county_keys,
                             county_basis=m.basis, county_note=m.note if isinstance(m.note, str) else "",
                             city_source=city_src, county_source=county_src))
    panel = pd.DataFrame(rows)
    for col in ["city_pop", "county_pop"]:
        panel[col] = panel[col].round().astype("Int64")
    panel["share_pct"] = panel["share_pct"].round(2)
    panel.to_csv(PROCESSED / "panel.csv", index=False)

    # Transcription check: Wikipedia/Forstall vs Census county file, overlapping years.
    ov = wiki.merge(avl, on=["county_key", "year"], suffixes=("_wiki", "_census"))
    ov = ov.dropna(subset=["population_census"])
    ov["diff"] = ov["population_wiki"] - ov["population_census"]
    ov["pct_diff"] = (100 * ov["diff"] / ov["population_census"]).round(3)
    ov[["county_key", "county_name_wiki", "year", "population_wiki", "population_census",
        "diff", "pct_diff"]].to_csv(PROCESSED / "validation_county_overlap.csv", index=False)

    # CESTA 2010 vs the 2020 table is not comparable, but flag shares > 100%.
    over = panel[panel.share_pct > 100.5]
    print(f"[panel] {len(panel)} rows, {panel.city_pop.notna().sum()} city obs, "
          f"{panel.county_pop.notna().sum()} county obs, {panel.share_pct.notna().sum()} shares")
    print(f"[panel] transcription check: {len(ov)} overlapping county-years, "
          f"{(ov['diff'] != 0).sum()} differ, max |pct diff| = {ov['pct_diff'].abs().max():.3f}%")
    if len(over):
        print("[panel] WARNING shares > 100%:\n", over[["city", "year", "city_pop", "county_pop", "share_pct"]])
    return panel


if __name__ == "__main__":
    build()
