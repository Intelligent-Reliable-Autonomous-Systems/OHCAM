"""Plot the relative success-rate drop under noise, averaged over domains.

Reads the per-domain ``*-by-noise-step-*.csv`` files in this directory (as written by
``scripts/aggregate_evals.py --noise-step``), takes the step-250 cross section, normalizes
each domain's curve by its own noise=0 success rate, and plots the mean over domains -- so
the y axis is "fraction of noise-free performance retained" and starts at 1.

Example:
    python scripts/plot_noise_scale.py --csv-dir results/<exp-id> --std-dev-shading
"""

import argparse
import csv as csv_module
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.legend_handler import HandlerBase  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
import numpy as np  # noqa: E402

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from aggregate_evals import (  # noqa: E402
    LABEL_SIZE,
    LEGEND_SIZE,
    MARGIN_BOTTOM,
    MARGIN_H,
    MARGIN_LEFT,
    MARGIN_W,
    TICK_LENGTH,
    TICK_SIZE,
    TICK_WIDTH,
    TITLE_SIZE,
    approach_label,
    color_for_approach,
    hatch_for_data,
    line_sort_key,
    linestyle_for_data,
    marker_kwargs,
    nice_ticks,
    zorder_for_line,
    zorder_for_shading,
)

SOLVE_RATE_COLUMN = "mean_avg-goal-reached"
DEFAULT_STEP = 250
BASELINE_NOISE_PCT = 0.0
# Only the --noise-step CSVs carry a noise_pct column; the --bar-step ones cover the same
# domains, so globbing both would count those domains twice.
CSV_GLOB = "*-by-noise-step-*.csv"
# One LaTeX column, kept short: this is the axes box, and the margins for labels are added
# on top, with bbox_inches="tight" cropping whatever goes unused.
DEFAULT_FIGSIZE = "2.9,1.1"
# The base font sizes are tuned for a 6x4in figure, so a column-width panel needs them down.
DEFAULT_FONT_SCALE = 0.55
BAR_GROUP_FRACTION = 0.8  # fraction of the per-noise slot filled by its bars


def read_points(csv_path: Path, step: int) -> dict[tuple[str, str], dict[float, float]]:
    """Map (approach, data source) -> noise pct -> success rate for one domain's CSV at ``step``.

    Each row's approach is a per-noise key ("conditional-sam.2"), which is one point on that
    approach's curve, so it is folded back to the approach itself. Keying on the data source
    alone would merge every approach's expert-data rows into one curve.
    """
    points: dict[tuple[str, str], dict[float, float]] = defaultdict(dict)
    with open(csv_path, newline="") as f:
        reader = csv_module.DictReader(f)
        if reader.fieldnames is None or "noise_pct" not in reader.fieldnames:
            print(f"warning: no noise_pct column, skipping: {csv_path.name}")
            return {}
        for row in reader:
            if int(row["step"]) != step:
                continue
            approach = row["approach"].partition(".")[0]
            points[(approach, row["data"])][float(row["noise_pct"])] = float(row[SOLVE_RATE_COLUMN])
    return points


def normalize(noise_to_rate: dict[float, float], label: str) -> dict[float, float] | None:
    """Divide a domain's curve by its noise=0 value, so it starts at 1."""
    baseline = noise_to_rate.get(BASELINE_NOISE_PCT)
    if baseline is None:
        print(f"warning: no noise={BASELINE_NOISE_PCT:g}% baseline, skipping: {label}")
        return None
    if baseline <= 0:
        print(f"warning: baseline is {baseline:g}, cannot normalize, skipping: {label}")
        return None
    return {noise: rate / baseline for noise, rate in noise_to_rate.items()}


# The two OHCAM data sources use the blue OHCAM color, with the expert one lightened; they are
# also told apart by line style / hatch. "train" is the current key for the expert traces and
# "eval" the legacy one; a sweep produces one or the other, never both.
OHCAM_LABELS = {"ohcam": "OHCAM (online)", "train": "OHCAM (expert)", "eval": "OHCAM (expert)"}


def _lighten(color, amount: float):
    """Blend a color toward white; amount in [0, 1], higher is lighter."""
    r, g, b = mcolors.to_rgb(color)
    return (r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount)


_OHCAM_BLUE = color_for_approach("ohcam")
OHCAM_COLORS = {"ohcam": _OHCAM_BLUE, "train": _lighten(_OHCAM_BLUE, 0.4),
                "eval": _lighten(_OHCAM_BLUE, 0.4)}
# Conditional-SAM and Cluster & Intersect are plotted from their own conditional-sam.<level> /
# predicators.<level> rows (run by scripts/run-noise.sh) exactly like the OHCAM series, and are
# simply absent from the figure for as long as a sweep's CSV has no rows for them.


def _square(patch: Patch, x: float, y: float, side: float, trans) -> Rectangle:
    """A square swatch copying a Patch's fill/edge/hatch, for square legend keys."""
    rect = Rectangle((x, y), side, side, facecolor=patch.get_facecolor(),
                     edgecolor=patch.get_edgecolor(), hatch=patch.get_hatch(),
                     linewidth=patch.get_linewidth())
    rect.set_transform(trans)
    return rect


class HandlerSquare(HandlerBase):
    """Draw a single Patch as a square (side = box height), centered in the handle slot.

    Keeps every swatch square regardless of the legend's handlelength.
    """

    def create_artists(self, legend, orig_handle, xdescent, ydescent, width, height, fontsize, trans):
        # Center the square in the handle box both ways, so it lines up with the label text
        # instead of spanning the full (taller) handle height and sitting high.
        side = min(width, height)
        x = xdescent + (width - side) / 2
        y = ydescent + (height - side) / 2
        return [_square(orig_handle, x, y, side, trans)]


def make_legend(series: list[dict], markers: dict, bar: bool,
                merge_ohcam: bool = True) -> tuple[list, list[str]]:
    """Build legend handles/labels.

    With ``merge_ohcam`` (the one-row layout), the two OHCAM series stay as separate keys but
    the online key is labeled just "/", so it reads as a separator between the two boxes and the
    expert key carries the full "OHCAM (online / expert)" label. Without it (the vertical
    layout), each OHCAM series is its own row with its own "OHCAM (online)"/"(expert)" label.
    Any non-OHCAM series (the baselines) follows with its own label either way.
    """
    def proxy(entry: dict):
        if bar:
            return Patch(facecolor=entry["color"], edgecolor="black", hatch=entry["hatch"])
        return Line2D([0], [0], color=entry["color"], linestyle=entry["linestyle"], **markers)

    handles: list = []
    labels: list[str] = []
    ohcam = [entry for entry in series if entry["approach"] == "ohcam"]
    for idx, entry in enumerate(ohcam):
        handles.append(proxy(entry))
        if merge_ohcam:
            labels.append("/" if idx == 0 else "OHCAM (online / expert)")
        else:
            # Break "OHCAM (online)" onto two lines with the qualifier indented.
            labels.append(entry["label"].replace(" (", "\n  ("))
    for entry in series:
        if entry["approach"] == "ohcam":
            continue
        handles.append(proxy(entry))
        labels.append(entry["label"])
    return handles, labels


def build_series(curves: dict[tuple[str, str], dict[float, list[float]]]) -> list[dict]:
    """Ordered plot series: the OHCAM curves per data source, then one per baseline."""
    series: list[dict] = []
    for approach, data_source in sorted(curves, key=line_sort_key):
        if approach == "ohcam":
            label = OHCAM_LABELS.get(data_source, data_source)
            color = OHCAM_COLORS.get(data_source, _OHCAM_BLUE)
        else:
            # The baselines are run on the expert data only, so the approach names the curve.
            label = approach_label(approach)
            color = color_for_approach(approach)
        noise_pcts = sorted(curves[(approach, data_source)])
        series.append({
            "approach": approach,
            "label": label,
            "color": color,
            "linestyle": linestyle_for_data(data_source),
            "hatch": hatch_for_data(data_source),
            "noise_pcts": noise_pcts,
            "means": [float(np.mean(curves[(approach, data_source)][n])) for n in noise_pcts],
            "std_devs": [float(np.std(curves[(approach, data_source)][n])) for n in noise_pcts],
        })
    return series


def collect(csv_paths: list[Path], step: int) -> dict[tuple[str, str], dict[float, list[float]]]:
    """Map (approach, data source) -> noise pct -> per-domain normalized rates."""
    curves: dict[tuple[str, str], dict[float, list[float]]] = defaultdict(lambda: defaultdict(list))
    for csv_path in csv_paths:
        for series_key, noise_to_rate in read_points(csv_path, step).items():
            approach, data_source = series_key
            normalized = normalize(noise_to_rate, f"{csv_path.name}/{approach}/{data_source}")
            if normalized is None:
                continue
            for noise_pct, rate in normalized.items():
                curves[series_key][noise_pct].append(rate)
    return curves


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv-dir", type=Path, default=Path(__file__).resolve().parent,
                        help=f"Directory of per-domain '{CSV_GLOB}' files (default: this script's).")
    parser.add_argument("--step", type=int, default=DEFAULT_STEP,
                        help=f"Step cross section to plot (default: {DEFAULT_STEP}).")
    parser.add_argument("--output", type=Path, default=None,
                        help="Path to save the plot (default: next to the CSVs).")
    parser.add_argument("--bar", action="store_true",
                        help="Draw grouped bars per noise level instead of lines.")
    parser.add_argument("--std-dev-shading", action="store_true",
                        help="Show one standard deviation across domains (shading, or bar error caps).")
    parser.add_argument("--figsize", type=str, default=DEFAULT_FIGSIZE,
                        help=f"Size of the plot box (the axes, not the canvas) as 'width,height' "
                             f"in inches (default: {DEFAULT_FIGSIZE}, one column and short).")
    parser.add_argument("--font-scale", type=float, default=DEFAULT_FONT_SCALE,
                        help=f"Scale all font sizes; sizes are tuned for a 6x4in figure "
                             f"(default: {DEFAULT_FONT_SCALE}, to match the default --figsize).")
    parser.add_argument("--marker-size", type=float, default=3.0,
                        help="Point marker size; 0 draws lines only (default: 3).")
    parser.add_argument("--line-width", type=float, default=1.5, help="Mean curve line width.")
    parser.add_argument("--num-xticks", type=int, default=5, help="Target number of x tick labels.")
    parser.add_argument("--num-yticks", type=int, default=5, help="Target number of y tick labels.")
    parser.add_argument("--legend-ncol", type=int, default=None,
                        help="Columns in the bottom legend (default: all entries on one row).")
    parser.add_argument("--legend-right", action="store_true",
                        help="Place a vertical legend to the right of the axes instead of a row "
                             "below it. The two OHCAM keys become their own rows.")
    parser.add_argument("--legend-top", action="store_true",
                        help="Put the horizontal legend above the axes in place of the title "
                             "(the title is dropped). Ignored if --legend-right is set.")
    parser.add_argument("--title", type=str, default=None, help="Override the panel title.")
    parser.add_argument("--pad-inches", type=float, default=0.01,
                        help="White border kept around the tight bounding box.")
    args = parser.parse_args()

    try:
        fig_w, fig_h = (float(x) for x in args.figsize.split(","))
    except ValueError:
        raise SystemExit("--figsize must be 'width,height', e.g. '6,4'.")
    if args.font_scale <= 0:
        raise SystemExit("--font-scale must be positive.")

    csv_paths = sorted(args.csv_dir.glob(CSV_GLOB))
    if not csv_paths:
        raise SystemExit(f"No '{CSV_GLOB}' files found in {args.csv_dir}.")
    curves = collect(csv_paths, args.step)
    if not curves:
        raise SystemExit(f"No usable results at step {args.step}.")

    label_size = LABEL_SIZE * args.font_scale
    markers = marker_kwargs(args.marker_size)

    fig = plt.figure(figsize=(fig_w + MARGIN_W, fig_h + MARGIN_H))
    ax = fig.add_axes([
        MARGIN_LEFT / (fig_w + MARGIN_W),
        MARGIN_BOTTOM / (fig_h + MARGIN_H),
        fig_w / (fig_w + MARGIN_W),
        fig_h / (fig_h + MARGIN_H),
    ])

    all_noise_pcts = sorted({noise for series in curves.values() for noise in series})
    series = build_series(curves)
    bar_width = BAR_GROUP_FRACTION / len(series)

    print(f"Relative solve rate at step {args.step} (mean over {len(csv_paths)} domains):")
    for series_idx, entry in enumerate(series):
        noise_pcts = entry["noise_pcts"]
        means = entry["means"]
        std_devs = entry["std_devs"]
        for noise_pct, mean, std_dev in zip(noise_pcts, means, std_devs):
            print(f"  {entry['label']} (noise={noise_pct:g}%): {mean:.4f} +/- {std_dev:.4f}")
        if args.bar:
            # Bars sit on evenly spaced slots, not the noise values: the group offsets would
            # otherwise have to be in noise-percent units and would collide.
            offset = (series_idx - (len(series) - 1) / 2) * bar_width
            slots = [all_noise_pcts.index(n) + offset for n in noise_pcts]
            ax.bar(slots, means, width=bar_width, color=entry["color"], edgecolor="black",
                   hatch=entry["hatch"], linewidth=0.8 * args.font_scale,
                   label=entry["label"], yerr=std_devs if args.std_dev_shading else None,
                   capsize=2 if args.std_dev_shading else 0,
                   error_kw={"linewidth": 0.8 * args.font_scale})
            continue
        if args.std_dev_shading:
            ax.fill_between(noise_pcts,
                            [m - s for m, s in zip(means, std_devs)],
                            [m + s for m, s in zip(means, std_devs)],
                            color=entry["color"], alpha=0.15, linewidth=0,
                            zorder=zorder_for_shading(entry["approach"]))
        ax.plot(noise_pcts, means, color=entry["color"], linestyle=entry["linestyle"],
                linewidth=args.line_width, label=entry["label"],
                zorder=zorder_for_line(entry["approach"]), **markers)

    ax.set_xlabel("noise %", fontsize=label_size, labelpad=4.0 * args.font_scale)
    ax.set_ylabel("relative completion", fontsize=label_size, labelpad=4.0 * args.font_scale)
    # --legend-top puts the horizontal legend where the title would go, so the title is dropped.
    if not args.legend_top:
        title = args.title if args.title is not None else "Relative Solve Rate vs Noise"
        ax.set_title(title, fontsize=TITLE_SIZE * args.font_scale, pad=6.0 * args.font_scale)
    ax.tick_params(labelsize=TICK_SIZE * args.font_scale, pad=3.5 * args.font_scale,
                   length=TICK_LENGTH * args.font_scale, width=TICK_WIDTH * args.font_scale)
    if args.bar:
        ax.set_xticks(range(len(all_noise_pcts)))
        ax.set_xticklabels([f"{n:g}" for n in all_noise_pcts])
    else:
        x_lo, x_hi = ax.dataLim.intervalx
        ax.set_xticks(nice_ticks(x_lo, x_hi, args.num_xticks))
    ax.set_yticks(nice_ticks(0.0, 1.0, args.num_yticks))
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    # bbox_inches="tight" grows the canvas to include the legend wherever it sits, so it never
    # steals from the fixed axes box.
    handler_map = {Patch: HandlerSquare()} if args.bar else {}
    if args.legend_right:
        # Vertical legend to the right: one row per key, so the OHCAM pair is not merged.
        handles, labels = make_legend(series, markers, args.bar, merge_ohcam=False)
        ax.legend(handles, labels, loc="center left", bbox_to_anchor=(1.0, 0.5), ncol=1,
                  fontsize=LEGEND_SIZE * args.font_scale, frameon=False, borderaxespad=0.0,
                  handlelength=1.0 if args.bar else 1.4, handletextpad=0.4,
                  labelspacing=0.4, handler_map=handler_map)
    elif args.legend_top:
        # Same one-row legend as the bottom layout, but anchored above the axes in the title's
        # place (the title is suppressed above).
        handles, labels = make_legend(series, markers, args.bar)
        ncol = args.legend_ncol if args.legend_ncol is not None else len(labels)
        ax.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 1.0),
                  ncol=ncol, fontsize=LEGEND_SIZE * args.font_scale, frameon=False,
                  columnspacing=0.8, handletextpad=0.3, handler_map=handler_map,
                  handlelength=1.0 if args.bar else 1.4)
    else:
        # Legend as a row below the x-axis. Merging the two OHCAM series leaves 4 entries, which
        # fit on one row by default (--legend-ncol). HandlerSquare keeps the swatches square and
        # compact; the "/"-labeled online box then sits right against the expert box.
        handles, labels = make_legend(series, markers, args.bar)
        ncol = args.legend_ncol if args.legend_ncol is not None else len(labels)
        ax.legend(handles, labels, loc="upper center",
                  bbox_to_anchor=(0.5, -0.28 * args.font_scale / DEFAULT_FONT_SCALE),
                  ncol=ncol, fontsize=LEGEND_SIZE * args.font_scale, frameon=False,
                  columnspacing=0.8, handletextpad=0.3, handler_map=handler_map,
                  handlelength=1.0 if args.bar else 1.4)

    if args.output is not None:
        output = args.output
    else:
        kind = "bar" if args.bar else "line"
        output = args.csv_dir / f"noise-scale-relative-{kind}-step-{args.step:03d}.png"
    fig.savefig(output, dpi=150, bbox_inches="tight", pad_inches=args.pad_inches)
    print(f"Wrote plot to {output}")


if __name__ == "__main__":
    main()
