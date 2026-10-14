"""Step 3: draw one chart per city from data/processed/panel.csv.

Each chart shows, for every decennial census 1800-2020:
  * a bar for the population inside city limits,
  * a bar beside it for the population of the county (or county-equivalent)
    containing the city in that year,
  * a line for the city's share of county population, on a right-hand
    0-100% axis.
Dashed vertical rules mark years where the comparison county changes
(e.g. Denver: Arapahoe County -> City and County of Denver in 1902).

Usage:  python make_graphs.py [--log]   (--log uses a log population axis)
Writes output/graphs/NN_city_id.png and output/graphs/all_cities.pdf
"""
import sys
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.ticker import FuncFormatter, PercentFormatter

from config import GRAPHS, PROCESSED, YEARS

CITY_C = "#2a78d6"     # categorical slot 1 (blue)
COUNTY_C = "#b4c6df"   # light tint of the same hue: the container of the city
SHARE_C = "#eb6834"    # categorical slot 2 (orange)
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def fmt_pop(x, _=None):
    if x >= 1e6:
        return f"{x / 1e6:.1f}M".replace(".0M", "M")
    if x >= 1e3:
        return f"{x / 1e3:.0f}K"
    return f"{x:.0f}"


SOURCES_NOTE = ("Sources: decennial census counts. City 1800–2010: Stanford CESTA compilation of U.S. Census "
                "Bureau place counts; city 2020: 2020 Census. County 1900–2020: Census county file "
                "(van Leuven); county 1800–1890: Forstall (1996), Population of States and Counties of the "
                "United States: 1790–1990.")


def city_footnotes(first, d):
    """Footnote lines for a city chart (shared with the static web app)."""
    notes = []
    if isinstance(first.get("city_notes"), str) and first.get("city_notes"):
        notes.append(first["city_notes"])
    if first.get("extends_beyond_principal_county") == "yes":
        notes.append("City limits extend beyond the comparison county, so the share slightly overstates "
                     "the share of that county living in the city.")
    for n in d["county_note"].dropna().unique():
        if n and n not in notes:
            notes.append(n)
    notes.append("Missing bars: city not enumerated / below reporting threshold, or county not yet organized.")
    notes.append(SOURCES_NOTE)
    return notes


def draw(city_df, log=False):
    d = city_df.set_index("year").reindex(YEARS)
    first = city_df.iloc[0]
    x = np.arange(len(YEARS))
    w = 0.38

    fig, ax = plt.subplots(figsize=(12, 6.6), dpi=150)
    fig.subplots_adjust(left=0.075, right=0.92, top=0.78, bottom=0.25)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(INK2)
    ax.spines["bottom"].set_color(INK2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)

    city = d["city_pop"].astype(float).values
    county = d["county_pop"].astype(float).values
    ax.bar(x - w / 2, city, w, color=CITY_C, label="City-limits population", zorder=2)
    ax.bar(x + w / 2, county, w, color=COUNTY_C, label="County population", zorder=2)
    if log:
        ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(fmt_pop))
    ax.set_ylabel("Population", color=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels(YEARS, rotation=45, ha="right", fontsize=9, color=INK2)
    ax.tick_params(axis="y", colors=INK2)
    ax.set_xlim(-0.7, len(YEARS) - 0.3)

    # Share line on a right-hand axis fixed at 0-100% so the scale is never inflated.
    ax2 = ax.twinx()
    share = d["share_pct"].astype(float).values
    ax2.plot(x, share, color=SHARE_C, lw=2, marker="o", ms=5, mec="white", mew=1.2,
             label="City share of county population (right axis)", zorder=3)
    top = max(100, np.nanmax(share) if np.isfinite(share).any() else 100)
    ax2.set_ylim(0, top * 1.05)
    ax2.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax2.set_ylabel("City share of county population", color=SHARE_C)
    ax2.tick_params(axis="y", colors=SHARE_C)
    for s in ["top", "left", "bottom"]:
        ax2.spines[s].set_visible(False)
    ax2.spines["right"].set_color(SHARE_C)

    # Project convention: no text labels on data lines; the legend identifies each series.

    # Mark changes in the comparison county.
    labels = d["county_label"].tolist()
    prev_i, level = -99, 0
    for i in range(1, len(labels)):
        if labels[i] != labels[i - 1] and isinstance(labels[i - 1], str):
            level = level + 1 if i - prev_i <= 3 else 0   # stagger neighbouring labels
            prev_i = i
            ax.axvline(i - 0.5, color=INK2, lw=0.9, ls=(0, (4, 3)), zorder=1)
            right = i > len(YEARS) - 8  # near the right edge: put text left of the rule
            txt = f"{YEARS[i]}: {labels[i]} \u2192" if right else f"\u2192 {YEARS[i]}: {labels[i]}"
            ax.text(i - 0.5, 1.012 + 0.045 * level, txt, transform=ax.get_xaxis_transform(),
                    fontsize=7.5, color=INK2, va="bottom", ha="right" if right else "left")

    # Titles
    pop20 = f"{int(first['city_pop_2020']):,}"
    fig.text(0.075, 0.955, f"{first['city']}, {first['state']}: city vs. county population, 1800–2020",
             fontsize=15, weight="bold", color=INK)
    county_now = d["county_label"].dropna().iloc[-1]
    fig.text(0.075, 0.915, f"#{first['rank']} city in the contiguous U.S. by 2020 Census population ({pop20}).  "
             f"Comparison county (2020): {county_now}.", fontsize=10, color=INK2)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    fig.legend(h1 + h2, l1 + l2, loc="upper left", bbox_to_anchor=(0.068, 0.905), ncol=3,
              frameon=False, fontsize=9)

    notes = city_footnotes(first, d)
    foot = "\n".join(textwrap.fill(n, 190) for n in notes)
    fig.text(0.075, 0.015, foot, fontsize=7, color=INK2, va="bottom", linespacing=1.35)
    return fig


def main(log=False):
    GRAPHS.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(PROCESSED / "panel.csv")
    cities = pd.read_csv(PROCESSED.parents[1] / "config" / "cities.csv")
    panel = panel.merge(cities[["city_id", "pop_2020", "extends_beyond_principal_county", "city_notes"]]
                        .rename(columns={"pop_2020": "city_pop_2020"}), on="city_id")
    suffix = "_log" if log else ""
    pdf_path = GRAPHS / f"all_cities{suffix}.pdf"
    with PdfPages(pdf_path) as pdf:
        for cid, g in panel.groupby("rank", sort=True):
            g = g.sort_values("year")
            fig = draw(g, log=log)
            name = f"{int(g['rank'].iloc[0]):02d}_{g['city_id'].iloc[0]}{suffix}.png"
            fig.savefig(GRAPHS / name)
            pdf.savefig(fig)
            plt.close(fig)
    print(f"[graphs] wrote {panel['city_id'].nunique()} PNGs and {pdf_path.name} to {GRAPHS}")


if __name__ == "__main__":
    main(log="--log" in sys.argv)
