"""Plot hypothesis-space size for OHCAM against Conditional SAM at d=1,2,3, per domain.

Reads the per-domain statistics written by the hscaling experiments:
OHCAM's count is ``overall.num_hypotheses`` from ``ohcam/statistics-ohcam-ohcam.json`` and
Conditional SAM's is ``hypothesis_space.total_hypotheses`` from
``samc-d<D>/statistics-samc-d<D>-ohcam.json``. One log-scale panel per domain, all sharing
the same y range so the cross-domain blow-up is comparable.

Example:
    python scripts/plot_hscaling.py --exp-name hscaling1 --extra-dir hscaling
"""

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.legend_handler import HandlerBase  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

SCRIPTS_DIR = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(SCRIPTS_DIR))

from aggregate_evals import (  # noqa: E402
    LABEL_SIZE,
    LEGEND_SIZE,
    TICK_LENGTH,
    TICK_SIZE,
    TICK_WIDTH,
    TITLE_SIZE,
    color_for_approach,
)

# Inches around the panel grid for the shared y label / ticks, the panel titles and the x tick
# labels. Smaller than aggregate_evals' single-panel margins because the y axis is shared and
# bbox_inches="tight" crops whatever the legend does not use -- so the left margin is generous
# and the y label sits at its outer edge, well clear of the tick labels.
MARGIN_LEFT = 0.85
MARGIN_RIGHT = 0.06
MARGIN_BOTTOM = 0.28
MARGIN_TOP = 0.26
MARGIN_W = MARGIN_LEFT + MARGIN_RIGHT
MARGIN_H = MARGIN_BOTTOM + MARGIN_TOP

# Domains in the order they appear across the paper's other figures, with display titles.
DOMAINS = [
    ("satellite", "Satellite"),
    ("maintenance", "Maintenance"),
    ("briefcase", "Briefcase"),
    ("miconic", "Miconic"),
    ("citycar", "CityCar"),
    ("nurikabe", "Nurikabe"),
]
DEPTHS = [1, 2, 3]

# OHCAM keeps its usual blue; the Conditional SAM bars are one orange hue stepped light -> dark,
# because d is ordinal -- the ramp says "same method, deeper" rather than "three methods".
OHCAM_COLOR = color_for_approach("ohcam")
SAMC_COLORS = {1: "#fdac66", 2: "#d95f02", 3: "#7f2704"}
OHCAM_LABEL = "OHCAM"
SAMC_LABEL = r"Cond-SAM $d\!=\!{}$"

# Sized for a 2x3 grid spanning a two-column page.
DEFAULT_FIGSIZE = "1.35,1.1"
DEFAULT_FONT_SCALE = 0.55
# The axis text (y label, tick labels, bar values) is the smallest type in the figure, so it runs
# larger than aggregate_evals' ratios; titles and legend keep the shared sizes.
AXIS_TEXT_BOOST = 1.25
BAR_WIDTH = 0.78
# Points between the bottom spine and the d labels, and inches between the panel titles and the
# legend that sits above them.
X_TICK_PAD = 5.0
LEGEND_PAD = 0.04
# Gap between a bar's top and its value label, in decades.
LABEL_GAP_DECADES = 0.11
# Slack above the tallest label, also in decades, so it never touches the top spine.
LABEL_HEADROOM_DECADES = 0.2


def read_counts(domain_dir: Path) -> dict[str, int]:
    """Map series key ('ohcam', 'd1', ...) -> hypothesis count for one domain."""
    counts: dict[str, int] = {}
    ohcam_path = domain_dir / "ohcam" / "statistics-ohcam-ohcam.json"
    if ohcam_path.exists():
        with open(ohcam_path) as f:
            counts["ohcam"] = int(json.load(f)["overall"]["num_hypotheses"])
    else:
        print(f"warning: missing {ohcam_path}")
    for depth in DEPTHS:
        samc_path = domain_dir / f"samc-d{depth}" / f"statistics-samc-d{depth}-ohcam.json"
        if not samc_path.exists():
            print(f"warning: missing {samc_path}")
            continue
        with open(samc_path) as f:
            counts[f"d{depth}"] = int(json.load(f)["hypothesis_space"]["total_hypotheses"])
    return counts


def format_count(value: int) -> str:
    """Compact bar label: 62, 1.4k, 298k, 1.2M."""
    if value < 1000:
        return str(value)
    if value < 10_000:
        return f"{value / 1000:.1f}k"
    if value < 1_000_000:
        return f"{round(value / 1000):.0f}k"
    return f"{value / 1_000_000:.1f}M"


class HandlerSquare(HandlerBase):
    """Draw a legend Patch as a square swatch, centered in the handle slot."""

    def create_artists(self, legend, orig_handle, xdescent, ydescent, width, height,
                       fontsize, trans):
        side = min(width, height)
        rect = Rectangle((xdescent + (width - side) / 2, ydescent + (height - side) / 2),
                         side, side, facecolor=orig_handle.get_facecolor(),
                         edgecolor=orig_handle.get_edgecolor(),
                         linewidth=orig_handle.get_linewidth())
        rect.set_transform(trans)
        return [rect]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exp-name", type=str, required=True,
                        help="Experiment name.")
    parser.add_argument("--extra-dir", type=str, default="",
                        help="Uses results from domains/<domain>/<extra-dir>/<exp-name>_1/.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Path to save the plot (default: results/<exp-name>/hypothesis-scaling.png"
                             "next to the results).")
    parser.add_argument("--grid", type=str, default="2x3",
                        help="Panel grid as 'rows x cols' (default: 2x3).")
    parser.add_argument("--figsize", type=str, default=DEFAULT_FIGSIZE,
                        help=f"Size of a single panel's axes box as 'width,height' in inches "
                             f"(default: {DEFAULT_FIGSIZE}).")
    parser.add_argument("--font-scale", type=float, default=DEFAULT_FONT_SCALE,
                        help=f"Scale all font sizes; sizes are tuned for a 6x4in figure "
                             f"(default: {DEFAULT_FONT_SCALE}).")
    parser.add_argument("--no-bar-labels", action="store_true",
                        help="Drop the count printed above each bar.")
    parser.add_argument("--pad-inches", type=float, default=0.01,
                        help="White border kept around the tight bounding box.")
    args = parser.parse_args()

    try:
        num_rows, num_cols = (int(x) for x in args.grid.lower().split("x"))
    except ValueError:
        raise SystemExit("--grid must be 'rows x cols', e.g. '2x3'.")
    if num_rows * num_cols < len(DOMAINS):
        raise SystemExit(f"--grid {args.grid} has no room for {len(DOMAINS)} domains.")
    try:
        panel_w, panel_h = (float(x) for x in args.figsize.split(","))
    except ValueError:
        raise SystemExit("--figsize must be 'width,height', e.g. '1.35,0.95'.")
    if args.font_scale <= 0:
        raise SystemExit("--font-scale must be positive.")

    counts_by_domain = {}
    for domain, title in DOMAINS:
        data_dir = Path(__file__).resolve().parents[1] / "domains" / domain /f"{args.extra_dir+'/' if args.extra_dir else ''}{args.exp_name}_1"
        if not data_dir.is_dir():
            print(f"warning: no experiment dir for {domain}, skipping")
            continue
        counts = read_counts(data_dir)
        if counts:
            counts_by_domain[domain] = counts
    if not counts_by_domain:
        raise SystemExit(f"No hypothesis-space statistics found under {data_dir}.")

    series = [("ohcam", OHCAM_LABEL, OHCAM_COLOR)]
    series += [(f"d{d}", SAMC_LABEL.format(d), SAMC_COLORS[d]) for d in DEPTHS]

    label_size = LABEL_SIZE * args.font_scale * AXIS_TEXT_BOOST
    tick_size = TICK_SIZE * args.font_scale * AXIS_TEXT_BOOST
    bar_label_size = tick_size * 0.85

    # One shared log y range across panels: the point of the figure is that the same axis holds
    # both a 10-hypothesis space and a 600k one. The top has to clear the tallest bar's value
    # label, whose height is in points rather than decades -- so solve for the number of decades
    # D that leaves room for it: D * (1 - label_height / panel_height) >= log10(top) + gaps.
    top = max(v for counts in counts_by_domain.values() for v in counts.values())
    y_lo = 1.0
    label_height_fraction = (bar_label_size * 1.3 / 72) / panel_h
    if label_height_fraction >= 0.5:
        raise SystemExit("Panel is too short for the bar labels; raise --figsize height.")
    decades = ((math.log10(top) + LABEL_GAP_DECADES + LABEL_HEADROOM_DECADES)
               / (1 - label_height_fraction))
    y_hi = 10 ** decades
    fig_w = panel_w * num_cols + MARGIN_W
    fig_h = panel_h * num_rows + MARGIN_H
    fig, axes = plt.subplots(num_rows, num_cols, figsize=(fig_w, fig_h), sharey=True)
    fig.subplots_adjust(
        left=MARGIN_LEFT / fig_w,
        right=1 - (MARGIN_W - MARGIN_LEFT) / fig_w,
        bottom=MARGIN_BOTTOM / fig_h,
        top=1 - (MARGIN_H - MARGIN_BOTTOM) / fig_h,
        wspace=0.12,
        hspace=0.7,
    )
    flat_axes = axes.flatten()

    print("Hypothesis-space size:")
    for panel_idx, (domain, title) in enumerate(DOMAINS):
        ax = flat_axes[panel_idx]
        counts = counts_by_domain.get(domain, {})
        print(f"  {title}: " + ", ".join(f"{key}={counts[key]}" for key, _, _ in series
                                         if key in counts))
        for bar_idx, (key, _, color) in enumerate(series):
            if key not in counts:
                continue
            value = counts[key]
            # Bars start at the axis floor rather than 0, which a log axis cannot draw.
            ax.bar(bar_idx, value - y_lo, bottom=y_lo, width=BAR_WIDTH, color=color,
                   edgecolor="black", linewidth=0.7 * args.font_scale, zorder=2)
            if not args.no_bar_labels:
                ax.text(bar_idx, value * 10 ** LABEL_GAP_DECADES, format_count(value),
                        ha="center", va="bottom", fontsize=bar_label_size, zorder=3)
        ax.set_yscale("log")
        ax.set_ylim(y_lo, y_hi)
        # Every other decade: the automatic locator drops to a 4-decade step on this range.
        ax.set_yticks([10.0 ** k for k in range(0, math.ceil(decades), 2)])
        ax.set_xlim(-0.5 - (1 - BAR_WIDTH) / 2, len(series) - 0.5 + (1 - BAR_WIDTH) / 2)
        ax.set_xticks(range(len(series)))
        # The bars are already named by the legend; the x axis just marks the d ladder.
        ax.set_xticklabels([""] + [rf"$d\!=\!{d}$" for d in DEPTHS])
        ax.set_title(title, fontsize=TITLE_SIZE * args.font_scale, pad=4.0 * args.font_scale)
        ax.tick_params(labelsize=tick_size, pad=2.5 * args.font_scale,
                       length=TICK_LENGTH * args.font_scale, width=TICK_WIDTH * args.font_scale)
        # No x ticks to hang off, so the d labels need their own pad to clear the bottom spine.
        ax.tick_params(axis="x", length=0, pad=X_TICK_PAD * args.font_scale)
        ax.grid(True, axis="y", alpha=0.3)
        ax.set_axisbelow(True)
    for ax in flat_axes[len(DOMAINS):]:
        ax.set_visible(False)

    # Pinned to the outer edge of the left margin, clear of the y tick labels; tight
    # cropping then trims whatever slack is left over.
    fig.supylabel("# hypotheses", fontsize=label_size, x=0.5 * MARGIN_LEFT / fig_w)
    handles = [Patch(facecolor=color, edgecolor="black", linewidth=0.7 * args.font_scale)
               for _, _, color in series]
    # Centered on the panel grid rather than on the figure, whose left margin would pull it off
    # center, and dropped to just above the top row's titles -- measured, since a title's height
    # depends on the font scale.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    top_row_top = max(ax.get_tightbbox(renderer).y1 for ax in flat_axes[:num_cols]) / fig.dpi
    fig.legend(handles, [label for _, label, _ in series], loc="lower center",
               bbox_to_anchor=((MARGIN_LEFT + panel_w * num_cols / 2) / fig_w,
                               (top_row_top + LEGEND_PAD) / fig_h),
               bbox_transform=fig.transFigure, ncol=len(series),
               fontsize=LEGEND_SIZE * args.font_scale, frameon=False, columnspacing=1.0,
               handletextpad=0.4, handlelength=1.0,
               handler_map={Patch: HandlerSquare()})

    output = args.output
    if output is None:
        output = Path(__file__).resolve().parents[1] / "results" / args.exp_name / "hypothesis-scaling.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=200, bbox_inches="tight", pad_inches=args.pad_inches)
    print(f"Wrote plot to {output}")


if __name__ == "__main__":
    main()
