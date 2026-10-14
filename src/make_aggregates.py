"""Step 3b: group averages of the city/county panel, for two grouping schemes.

  region  National (all 100 cities) and the four Census regions (Northeast,
          Midwest, South, West), assigned by state.
  size    All cities and the four quartiles of 2020 city land area (25 cities
          each; config/city_land_area.csv). Quartiles use 2020 boundaries for
          every year, so they classify cities by today's size, not their size
          at the time (many grew by annexation).

For each group and census year, the sample is the cities with BOTH a city and a
county population that year (n is printed under each year). Then:
  * bars  = mean city-limits population and mean county population
  * line  = average city share of county population, in two versions:
      unweighted   simple mean of the city shares, each city counts equally
      weighted     population-weighted mean of the shares, weighting each city
                   by its county population. Equivalently,
                   sum(city pop) / sum(county pop) = ratio of the two bars.
Counties containing several top-100 cities (e.g. Maricopa, Los Angeles, Dallas)
enter once per city.

Outputs
-------
data/processed/aggregates.csv                (column `scheme` = region | size)
output/graphs/aggregates/agg_<group>_<weighting>.png   region charts (10)
output/graphs/aggregates/compare_<weighting>.png       region share comparison (2)
output/graphs/aggregates/size_<group>_<weighting>.png  size-quartile charts (10)
output/graphs/aggregates/size_compare_<weighting>.png  size share comparison (2)
output/graphs/averages.pdf, output/graphs/city_size.pdf (one chart per page)
"""
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.ticker import FuncFormatter, PercentFormatter

from config import CONFIG, GRAPHS, PROCESSED, YEARS
from make_graphs import CITY_C, COUNTY_C, GRID, INK, INK2, SHARE_C, fmt_pop

AGG_DIR = GRAPHS / "aggregates"

# U.S. Census Bureau regions (contiguous states only are relevant here).
REGION_STATES = {
    "Northeast": ["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"],
    "Midwest": ["IL", "IN", "IA", "KS", "MI", "MN", "MO", "NE", "ND", "OH", "SD", "WI"],
    "South": ["AL", "AR", "DE", "DC", "FL", "GA", "KY", "LA", "MD", "MS", "NC", "OK", "SC",
              "TN", "TX", "VA", "WV"],
    "West": ["AZ", "CA", "CO", "ID", "MT", "NV", "NM", "OR", "UT", "WA", "WY"],
}
STATE_REGION = {s: r for r, ss in REGION_STATES.items() for s in ss}
WEIGHTINGS = {"unweighted": "Unweighted", "weighted": "Population-weighted"}
REGIONS = ["Northeast", "Midwest", "South", "West"]
QUARTILES = ["Q1", "Q2", "Q3", "Q4"]


def size_quartiles():
    """Assign the 100 cities to 2020 land-area quartiles of exactly 25 (ties broken by rank)."""
    a = pd.read_csv(CONFIG / "city_land_area.csv")
    cities = pd.read_csv(CONFIG / "cities.csv")[["city_id", "rank"]]
    a = a.merge(cities, on="city_id").sort_values(["land_area_sqmi_2020", "rank"]).reset_index(drop=True)
    a["group"] = [QUARTILES[i * 4 // len(a)] for i in range(len(a))]
    return a


def make_schemes():
    q = size_quartiles()
    rng = q.groupby("group").land_area_sqmi_2020.agg(["min", "max"])
    size_names = {g: f"{g}: {rng.loc[g, 'min']:.1f}–{rng.loc[g, 'max']:.1f} sq mi" for g in QUARTILES}
    short = {"Q1": "Q1 (smallest)", "Q2": "Q2", "Q3": "Q3", "Q4": "Q4 (largest)"}
    return {
        "region": dict(
            all_label="National", groups=REGIONS, prefix="agg", compare="compare", pdf="averages.pdf",
            names={g: g for g in REGIONS},
            member=lambda df: df["state"].map(STATE_REGION),
            title=lambda g: "National average" if g == "National" else f"{g} region average",
            scope=lambda g, n: "all 100 cities" if g == "National" else f"{n} cities in the {g}",
            compare_title="national and Census regions",
            # national in ink, regions in categorical slots 1-4 (fixed order)
            colors={"National": INK, "Northeast": "#2a78d6", "Midwest": "#eb6834",
                    "South": "#1baf7a", "West": "#eda100"},
            member_note=lambda g: f"{g} (U.S. Census region)"),
        "size": dict(
            all_label="National", groups=QUARTILES, prefix="size", compare="size_compare", pdf="city_size.pdf",
            names=size_names, assign=dict(zip(q.city_id, q.group)),
            member=None,
            title=lambda g: "All cities average" if g == "National" else f"Land-area {short[g]} average",
            scope=lambda g, n: ("all 100 cities" if g == "National"
                                else f"{n} cities with 2020 land area {size_names[g].split(': ')[1]}"),
            compare_title="all cities and city land-area quartiles",
            # quartiles are ordered: one blue ramp light->dark; all-cities in categorical orange
            colors={"National": "#eb6834", "Q1": "#86b6ef", "Q2": "#3987e5", "Q3": "#1c5cab", "Q4": "#0d366b"},
            member_note=lambda g: f"Land-area {short[g]}"),
    }


def group_of(panel, scheme):
    return panel["city_id"].map(scheme["assign"]) if scheme.get("assign") else scheme["member"](panel)


def compute(panel, scheme_key, scheme):
    panel = panel.copy()
    panel["grp"] = group_of(panel, scheme)
    rows = []
    for g in ["National"] + scheme["groups"]:
        sub = panel if g == "National" else panel[panel.grp == g]
        n_members = sub.city_id.nunique()
        for y in YEARS:
            m = sub[(sub.year == y) & sub.city_pop.notna() & sub.county_pop.notna()]
            n = len(m)
            base = dict(scheme=scheme_key, group=g, year=y, n_cities=n, n_group=n_members)
            if n == 0:
                for wkey in WEIGHTINGS:
                    rows.append({**base, "weighting": wkey, "mean_city_pop": np.nan,
                                 "mean_county_pop": np.nan, "share_pct": np.nan})
                continue
            mc, mk = m.city_pop.mean(), m.county_pop.mean()
            unw = (100 * m.city_pop / m.county_pop).mean()
            wtd = 100 * m.city_pop.sum() / m.county_pop.sum()
            for wkey, share in [("unweighted", unw), ("weighted", wtd)]:
                rows.append({**base, "weighting": wkey, "mean_city_pop": round(mc),
                             "mean_county_pop": round(mk), "share_pct": round(share, 2)})
    return pd.DataFrame(rows)


def style_axes(ax):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(INK2)
    ax.spines["bottom"].set_color(INK2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def year_labels(ns):
    return [f"{y}\nn={n}" for y, n in zip(YEARS, ns)]


def group_notes(members, group, wkey, scheme):
    """Footnote lines for a group-average chart (shared with the static web app)."""
    notes = [
        "Each year averages only the cities with both a city and a county count that year (n under each year), "
        "so the sample grows over time and early years rest on few cities. Counties containing several of the "
        "cities count once per city. Consolidated city-counties (share near 100%) raise the averages.",
    ]
    ny_group = group == "National" or "New York, NY" in members
    if wkey == "weighted" and ny_group:
        notes.append("New York's comparison area is its five boroughs (share 100%), and its size dominates this "
                     "population-weighted average from 1900 on.")
    if scheme["prefix"] == "size":
        notes.append("Quartiles use 2020 land area for every year: they group cities by today's size, not their "
                     "size at the time (many cities grew by annexation).")
    if group != "National":
        notes.append(scheme["member_note"](group) + ": " + ", ".join(members) + ".")
    notes.append("Sources: decennial census counts (see README); city-level charts give per-city definitions and notes.")
    return notes


def draw_group(agg, members, group, wkey, scheme):
    d = agg[(agg.group == group) & (agg.weighting == wkey)].set_index("year").reindex(YEARS)
    x = np.arange(len(YEARS))
    w = 0.38
    fig, ax = plt.subplots(figsize=(12, 6.6), dpi=150)
    fig.subplots_adjust(left=0.075, right=0.92, top=0.78, bottom=0.31)
    style_axes(ax)
    ax.bar(x - w / 2, d.mean_city_pop.values, w, color=CITY_C, label="Mean city-limits population", zorder=2)
    ax.bar(x + w / 2, d.mean_county_pop.values, w, color=COUNTY_C, label="Mean county population", zorder=2)
    ax.yaxis.set_major_formatter(FuncFormatter(fmt_pop))
    ax.set_ylabel("Population (mean across cities)", color=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels(year_labels(d.n_cities.fillna(0).astype(int)), fontsize=7.5, color=INK2)
    ax.tick_params(axis="y", colors=INK2)
    ax.set_xlim(-0.7, len(YEARS) - 0.3)

    ax2 = ax.twinx()
    share = d.share_pct.values.astype(float)
    lab = ("Mean city share of county population" if wkey == "unweighted"
           else "Population-weighted city share of county population")
    ax2.plot(x, share, color=SHARE_C, lw=2, marker="o", ms=5, mec="white", mew=1.2,
             label=lab + " (right axis)", zorder=3)
    ax2.set_ylim(0, 105)
    ax2.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax2.set_ylabel("City share of county population", color=SHARE_C)
    ax2.tick_params(axis="y", colors=SHARE_C)
    for s in ["top", "left", "bottom"]:
        ax2.spines[s].set_visible(False)
    ax2.spines["right"].set_color(SHARE_C)
    # Project convention: no text labels on data lines; the legend identifies each series.

    scope = scheme["scope"](group, len(members))
    title = scheme["title"](group)
    fig.text(0.075, 0.955, f"{title}: city vs. county population, 1800–2020 ({WEIGHTINGS[wkey].lower()})",
             fontsize=15, weight="bold", color=INK)
    sub = ("Line: simple mean of city shares." if wkey == "unweighted" else
           "Line: total city pop. ÷ total county pop. (ratio of the bars).")
    fig.text(0.075, 0.915, f"Top-100 contiguous-U.S. cities (2020), {scope}. {sub}",
             fontsize=9.5, color=INK2)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    fig.legend(h1 + h2, l1 + l2, loc="upper left", bbox_to_anchor=(0.068, 0.905), ncol=3,
               frameon=False, fontsize=9)

    notes = group_notes(members, group, wkey, scheme)
    foot = "\n".join(textwrap.fill(n, 200) for n in notes)
    fig.text(0.075, 0.012, foot, fontsize=7, color=INK2, va="bottom", linespacing=1.35)
    return fig


def draw_compare(agg, wkey, scheme):
    x = np.arange(len(YEARS))
    fig, ax = plt.subplots(figsize=(12, 6.0), dpi=150)
    fig.subplots_adjust(left=0.075, right=0.97, top=0.82, bottom=0.17)
    style_axes(ax)
    for g in ["National"] + scheme["groups"]:
        d = agg[(agg.group == g) & (agg.weighting == wkey)].set_index("year").reindex(YEARS)
        y = d.share_pct.values.astype(float)
        nat = g == "National"
        lab = ("All cities" if scheme["prefix"] == "size" else "National") if nat else scheme["names"][g]
        ax.plot(x, y, color=scheme["colors"][g], lw=2.6 if nat else 2, marker="o", ms=4.5 if nat else 4,
                mec="white", mew=1, label=lab, zorder=4 if nat else 3, ls=(0, (5, 2)) if nat and scheme["prefix"] == "size" else "-")
    # Project convention: no text labels on data lines; the legend identifies each series.
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_ylabel("City share of county population", color=INK2)
    ax.tick_params(axis="y", colors=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels(YEARS, rotation=45, ha="right", fontsize=9, color=INK2)
    ax.set_xlim(-0.5, len(YEARS) - 0.5)
    fig.text(0.075, 0.94, f"Average city share of county population: {scheme['compare_title']} "
             f"({WEIGHTINGS[wkey].lower()})", fontsize=14, weight="bold", color=INK)
    sub = ("Simple mean of city shares" if wkey == "unweighted"
           else "Shares weighted by county population (total city ÷ total county pop.)")
    fig.text(0.075, 0.90, f"Top 100 contiguous-U.S. cities (2020). {sub}; each year uses cities with both counts.",
             fontsize=9.5, color=INK2)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.08), ncol=5, frameon=False, fontsize=9)
    extra = (" Quartiles use 2020 land area for every year." if scheme["prefix"] == "size" else "")
    fig.text(0.075, 0.02, "Early years rest on few cities per group (see the n counts in the group charts)."
             + extra + " Sources: decennial census counts (see README).", fontsize=7, color=INK2)
    return fig


def main():
    AGG_DIR.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(PROCESSED / "panel.csv")
    cities = panel.drop_duplicates("city_id")[["rank", "city_id", "city", "state"]].sort_values("rank")
    schemes = make_schemes()
    out = []
    for skey, sc in schemes.items():
        agg = compute(panel, skey, sc)
        out.append(agg)
        cities["grp"] = group_of(cities, sc)
        with PdfPages(GRAPHS / sc["pdf"]) as pdf:
            for g in ["National"] + sc["groups"]:
                mem = cities if g == "National" else cities[cities.grp == g]
                members = [f"{r.city}, {r.state}" for r in mem.itertuples()]
                for wkey in WEIGHTINGS:
                    fig = draw_group(agg, members, g, wkey, sc)
                    fig.savefig(AGG_DIR / f"{sc['prefix']}_{g.lower()}_{wkey}.png")
                    pdf.savefig(fig)
                    plt.close(fig)
            for wkey in WEIGHTINGS:
                fig = draw_compare(agg, wkey, sc)
                fig.savefig(AGG_DIR / f"{sc['compare']}_{wkey}.png")
                pdf.savefig(fig)
                plt.close(fig)
        print(f"[averages] {skey}: groups {cities.grp.value_counts().sort_index().to_dict()}; "
              f"wrote 12 charts and {sc['pdf']}")
    allagg = pd.concat(out, ignore_index=True)
    allagg.to_csv(PROCESSED / "aggregates.csv", index=False)
    return allagg


if __name__ == "__main__":
    main()
