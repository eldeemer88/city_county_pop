"""Shared paths and constants for the city/county population project."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
GRAPHS = ROOT / "output" / "graphs"
DB_PATH = ROOT / "output" / "city_pop.db"

YEARS = list(range(1800, 2030, 10))  # 1800, 1810, ..., 2020

# Remote sources, pinned to specific commits so downloads are reproducible.
SOURCES = {
    "cesta": {
        "file": RAW / "cesta_1790-2010_MASTER.csv",
        "url": "https://raw.githubusercontent.com/cestastanford/historical-us-city-populations/"
               "9b267baf1a7a662ca2076cc966166662346f80bc/data/1790-2010_MASTER.csv",
        "sha256": "4beb74cf86adb57bdd8d8481022b670af7299447dad78a5ed27c99337c0a83d7",
        "citation": "Steiner, E. and Heppler, J. A. 'United States Historical City Populations, "
                    "1790-2010.' Stanford CESTA. Compiled primarily from U.S. Census Bureau "
                    "decennial counts of incorporated places.",
    },
    "vanleuven": {
        "file": RAW / "vanleuven_historical_county_populations_v2.csv",
        "url": "https://raw.githubusercontent.com/andrewvanleuven/website/"
               "51b9704bc0212040b1137d8e5540097131cad254/static/files/data/"
               "historical_county_populations_v2.csv",
        "sha256": "eb501876ee3cf86d6f8298f2191ef1f4eee162553364cc124d9526e323c924f8",
        "citation": "Van Leuven, A. J. 'Historical U.S. County Population Data: 1900 to 2020.' "
                    "Census Bureau 'Population of Counties by Decennial Census: 1900 to 1990' "
                    "plus 2000-2020 decennial counts (doi:10.7910/DVN/WLS5GF).",
    },
}
WIKI_COUNTY_FILE = RAW / "county_wikipedia_transcribed.csv"
