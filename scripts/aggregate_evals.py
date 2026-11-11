"""Aggregate baseline eval results over iterations and plot a metric by step.

Reads the per-step results JSONs written by ``ohcam.metrics.eval``
(via ``scripts/eval-learn100.sh``), averages a metric over the
``<exp_id>_<iter>`` iterations, and plots one line per ``(approach, data)``.

Example:
    python scripts/aggregate_evals.py \
        --config domains/maintenance/experiment.json \
        --exp-id run1 \
        --num-iters 5
"""

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402
import numpy as np  # noqa: E402

SOLVE_RATE_METRIC = "avg-goal-reached"
STEP_RE = re.compile(r"^(?P<data>.+)-step-(?P<step>\d+)$")
DOMAIN_RE = re.compile(r"\(define\s*\(domain\s+([\w-]+)\s*\)", re.IGNORECASE)

# Fixed colors per approach so a given approach looks the same across configs.
APPROACH_COLORS = {
    "ohcam": "tab:blue",
    "conditional-sam": "tab:orange",
    "predicators": "tab:green",
    "olam": "tab:red",
    "random": "tab:purple",
    "lamp": "tab:brown",
    "lamp2": "tab:pink",
}
# Fixed line styles per data source. "train" is the current key for the expert traces and
# "eval" the legacy one; a sweep produces one or the other, never both.
DATA_LINESTYLES = {
    "ohcam": "-",
    "eval": "-.",
    "train": "-.",
    "random": ":",
    "olam": "--",
}
_FALLBACK_LINESTYLES = ["-", "--", ":", "-."]
DATA_HATCHES = {
    "ohcam": "",
    "eval": "///",
    "train": "///",
    "random": "...",
    "olam": "\\\\",
}
_FALLBACK_HATCHES = ["", "///", "\\\\", "...", "xxx", "++", "oo"]
DATA_LABELS = {
    "ohcam": "OHCAM data",
    "eval": "Expert data",
    "train": "Expert data",
    "random": "Random data",
    "olam": "OLAM data",
}
APPROACH_LABELS = {
    "ohcam": "OHCAM",
    "conditional-sam": "Conditional SAM",
    "predicators": "Cluster&Intersect",
    "olam": "OLAM",
    "random": "Random",
    "lamp": "LAMP",
    "lamp2": "LAMP2",
}

# The approaches a noise-scale sweep varies the noise of, i.e. the ones --noise-step plots.
NOISE_APPROACH_TYPES = ("ohcam", "conditional-sam", "predicators")

# Legend/plot ordering: ohcam first, then the rest.
APPROACH_ORDER = {name: i for i, name in enumerate(
    ["ohcam", "conditional-sam", "predicators", "olam", "random", "lamp", "lamp2"])}
DATA_ORDER = {name: i for i, name in enumerate(["ohcam", "eval", "train", "random", "olam"])}

# Lines stack by APPROACH_ORDER: the first approach listed draws on top of the second, and so
# on, so overlapping curves resolve by that ranking rather than by draw order. Approaches not
# listed fall to the bottom. Shading is kept below every line (and below the gridlines, which
# axisbelow="line" puts at 1.5) but ranked the same way among the bands themselves.
LINE_ZORDER_BASE = 2.0
SHADING_ZORDER_BASE = 0.6
SHADING_ZORDER_SPREAD = 0.05

# Inches reserved around the axes box for the title/labels/ticks. Deliberately generous: it only
# has to be big enough at --font-scale 1, and bbox_inches="tight" crops whatever goes unused, so
# a hidden y-label just yields a narrower image rather than a resized plot box.
MARGIN_LEFT = 1.1
MARGIN_RIGHT = 0.3
MARGIN_BOTTOM = 0.9
MARGIN_TOP = 0.6
MARGIN_W = MARGIN_LEFT + MARGIN_RIGHT
MARGIN_H = MARGIN_BOTTOM + MARGIN_TOP

# Base font sizes, tuned for the default 6x4in figure; --font-scale multiplies them.
TITLE_SIZE = 20
LABEL_SIZE = 16
TICK_SIZE = 13
LEGEND_SIZE = 14
DEFAULT_MARKER_SIZE = 0.0

# Matplotlib's default pads (points), also scaled by --font-scale.
LABEL_PAD = 4.0
TICK_PAD = 3.5
TITLE_PAD = 6.0
TICK_LENGTH = 3.5
TICK_WIDTH = 0.8
# Allowed tick intervals; 2.5 is what lets a 0..100 axis land on 0/25/50/75/100.
TICK_STEPS = [1, 2, 2.5, 5, 10]


def nice_ticks(lo: float, hi: float, num_ticks: int) -> list[float]:
    """Round tick values spanning [lo, hi], aiming for ``num_ticks`` of them."""
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        return []
    locator = MaxNLocator(nbins=num_ticks - 1, steps=TICK_STEPS)
    eps = (hi - lo) * 1e-9  # keep endpoint ticks that float error nudges out of range
    return [t for t in locator.tick_values(lo, hi) if lo - eps <= t <= hi + eps]


def marker_kwargs(marker_size: float) -> dict:
    """Marker style for line plots; a size of 0 draws lines only."""
    if marker_size <= 0:
        return {"marker": None}
    return {"marker": "o", "markersize": marker_size}


def line_sort_key(key: tuple[str, str]) -> tuple:
    approach, data_source = key
    return (
        APPROACH_ORDER.get(approach, len(APPROACH_ORDER)), approach,
        DATA_ORDER.get(data_source, len(DATA_ORDER)), data_source,
    )


def approach_rank(approach: str) -> int:
    """Position in APPROACH_ORDER; unlisted approaches (e.g. "ohcam.05") rank last."""
    if approach in APPROACH_ORDER:
        return APPROACH_ORDER[approach]
    # Per-noise keys ("ohcam.05") route to the ohcam agent, so they stack like it.
    if approach.startswith("ohcam."):
        return APPROACH_ORDER["ohcam"]
    return len(APPROACH_ORDER)


def zorder_for_line(approach: str) -> float:
    """Earlier in APPROACH_ORDER draws on top."""
    return LINE_ZORDER_BASE + (len(APPROACH_ORDER) - approach_rank(approach))


def zorder_for_shading(approach: str) -> float:
    """Shading sits below every line, not just its own, and ranks like the lines among itself.

    Tying a band to its own line's zorder would let a high-ranked approach's band cover every
    lower-ranked approach's curve, tinting and hiding them.
    """
    return SHADING_ZORDER_BASE + (len(APPROACH_ORDER) - approach_rank(approach)) * SHADING_ZORDER_SPREAD


def approach_label(approach: str) -> str:
    return APPROACH_LABELS.get(approach, approach)


def approach_legend_linestyle(approach: str) -> str:
    return linestyle_for_data("olam") if approach == "olam" else "-"


def make_legend(keys: list[tuple[str, str]], bar_chart: bool = False,
                square_approach_handles: bool = False,
                marker_size: float = DEFAULT_MARKER_SIZE) -> tuple[list[Line2D | Patch], list[str]]:
    approaches = sorted({approach for approach, _ in keys},
                        key=lambda approach: (APPROACH_ORDER.get(approach, len(APPROACH_ORDER)), approach))

    handles: list[Line2D | Patch] = []
    labels: list[str] = []
    markers = marker_kwargs(marker_size)

    data_sources = ("ohcam", "eval", "random") if not bar_chart else sorted(
        {data_source for _, data_source in keys},
        key=lambda data_source: (DATA_ORDER.get(data_source, len(DATA_ORDER)), data_source),
    )
    for data_source in data_sources:
        if bar_chart:
            handles.append(Patch(facecolor="white", edgecolor="black", hatch=hatch_for_data(data_source)))
            labels.append(DATA_LABELS.get(data_source, data_source))
        else:
            handles.append(Line2D([0], [0], color="black",
                                  linestyle=linestyle_for_data(data_source), **markers))
            labels.append(DATA_LABELS.get(data_source, data_source))

    for approach in approaches:
        if bar_chart or square_approach_handles:
            handles.append(Patch(facecolor=color_for_approach(approach), edgecolor="black"))
            labels.append(approach_label(approach))
        else:
            handles.append(Line2D([0], [0], color=color_for_approach(approach),
                                  linestyle=approach_legend_linestyle(approach), **markers))
            labels.append(approach_label(approach))

    return handles, labels


def make_wide_legend(keys: list[tuple[str, str]],
                     marker_size: float = DEFAULT_MARKER_SIZE) -> tuple[list[Line2D | Patch], list[str]]:
    """Single-row legend: the three data sources as line styles, then a color box per approach.

    OLAM is the exception: it trains on its own data rather than one of the three shared sources,
    so a color box would imply a data/approach combination that does not exist. It goes last, as
    its own red line.
    """
    markers = marker_kwargs(marker_size)
    handles: list[Line2D | Patch] = []
    labels: list[str] = []

    for data_source in ("ohcam", "eval", "random"):
        handles.append(Line2D([0], [0], color="black",
                              linestyle=linestyle_for_data(data_source), **markers))
        labels.append(DATA_LABELS.get(data_source, data_source))

    approaches = sorted({approach for approach, _ in keys},
                        key=lambda approach: (APPROACH_ORDER.get(approach, len(APPROACH_ORDER)), approach))
    for approach in approaches:
        if approach == "olam":
            continue
        label = approach_label(approach)
        if label in labels:
            continue
        handles.append(Patch(facecolor=color_for_approach(approach), edgecolor="black"))
        labels.append(label)

    if "olam" in approaches:
        handles.append(Line2D([0], [0], color=color_for_approach("olam"),
                              linestyle=linestyle_for_data("olam"), **markers))
        labels.append(approach_label("olam"))

    return handles, labels




def _stable_index(key: str, n: int) -> int:
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % n


def color_for_approach(approach: str):
    if approach in APPROACH_COLORS:
        return APPROACH_COLORS[approach]
    palette = plt.get_cmap("tab20").colors
    return palette[_stable_index(approach, len(palette))]


def linestyle_for_data(data_source: str) -> str:
    if data_source in DATA_LINESTYLES:
        return DATA_LINESTYLES[data_source]
    return _FALLBACK_LINESTYLES[_stable_index(data_source, len(_FALLBACK_LINESTYLES))]


def hatch_for_data(data_source: str) -> str:
    if data_source in DATA_HATCHES:
        return DATA_HATCHES[data_source]
    return _FALLBACK_HATCHES[_stable_index(data_source, len(_FALLBACK_HATCHES))]


def approach_types_from_config(config: Path) -> dict[str, str]:
    """Map each approach key to its agent type (``approach`` field), defaulting to the key.

    The same agent runs under multiple keys (e.g. ``ohcam.05``
    routes to ``ohcam``). Online runs use the key itself as their data source, so we use
    this map to recover the underlying data type (``ohcam``/``eval``/``random``/...).
    """
    try:
        cfg = json.loads(config.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    types: dict[str, str] = {}
    for key, spec in cfg.get("approaches", {}).items():
        types[key] = spec.get("approach", key) if isinstance(spec, dict) else key
    return types


def noise_values_from_config(config: Path) -> dict[str, float]:
    """Map each noise-scale key to its noise level, for plotting.

    A noise-scale config declares one key per approach per noise level (``ohcam.05``,
    ``conditional-sam.05``, ``predicators.05``, ...), all of which scripts/run-noise.sh runs.
    The OHCAM keys carry the level as ``config.noise``; the baseline keys have no ``config``
    block, so theirs comes from the key suffix, which is the same fraction.
    """
    try:
        cfg = json.loads(config.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    noise_by_key: dict[str, float] = {}
    for key, spec in cfg.get("approaches", {}).items():
        if not isinstance(spec, dict):
            continue
        approach_type = spec.get("approach", key)
        if approach_type not in NOISE_APPROACH_TYPES:
            continue
        config_params = spec.get("config", {})
        if isinstance(config_params, dict) and "noise" in config_params:
            noise_by_key[key] = float(config_params["noise"])
            continue
        suffix = key.partition(".")[2]
        if suffix.isdigit():
            noise_by_key[key] = float(f"0.{suffix}")
    return noise_by_key


def data_sort_key(data_source: str) -> tuple:
    return (DATA_ORDER.get(data_source, len(DATA_ORDER)), data_source)




def make_noise_step_legend(series_keys: list[tuple[str, str]],
                           marker_size: float = DEFAULT_MARKER_SIZE) -> tuple[list[Line2D], list[str]]:
    """Compact legend for noise-step plots: one key per (approach, data source) curve.

    OHCAM's keys are labeled by data source alone, as it is the only approach run on more than
    one; the baselines, all on the expert data, are labeled by approach instead.
    """
    handles: list[Line2D] = []
    labels: list[str] = []
    for approach_type, data_source in series_keys:
        handles.append(Line2D([0], [0], color=color_for_approach(approach_type),
                              linestyle=linestyle_for_data(data_source),
                              **marker_kwargs(marker_size)))
        data_label = DATA_LABELS.get(data_source, data_source)
        labels.append(data_label if approach_type == "ohcam" else approach_label(approach_type))
    return handles, labels


def get_gt_domain_name(config: Path) -> str:
    """Return the ground-truth PDDL domain name from the config's gt_domain file."""
    try:
        cfg = json.loads(config.read_text())
    except (OSError, json.JSONDecodeError):
        return config.stem
    gt_domain = cfg.get("gt_domain")
    if not gt_domain:
        return config.stem
    gt_path = (config.parent / gt_domain).resolve()
    try:
        match = DOMAIN_RE.search(gt_path.read_text())
    except OSError:
        return gt_path.stem
    return match.group(1) if match else gt_path.stem


def parse_result_filename(result_file: Path, approach: str) -> tuple[str, int] | None:
    """Return (data_source, step) for a step-indexed results file, else None."""
    prefix = f"results-{approach}-"
    name = result_file.stem
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    match = STEP_RE.match(rest)
    if match is None:
        return None  # non-step result file (e.g. results-<approach>-<data>.json)
    return match.group("data"), int(match.group("step"))


def collect_results(config: Path, exp_id: str, num_iters: int, metric: str, omit: list[str]):
    """Map (approach, data) -> step -> list of metric values across iterations."""
    config_dir = config.parent
    approach_types = approach_types_from_config(config)
    aggregated: dict[tuple[str, str], dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

    for it in range(1, num_iters + 1):
        exp_dir = config_dir / f"{exp_id}_{it}"
        if not exp_dir.is_dir():
            print(f"warning: experiment dir not found, skipping: {exp_dir}")
            continue
        for approach_dir in sorted(p for p in exp_dir.iterdir() if p.is_dir()):
            approach = approach_dir.name
            if approach in omit:
                continue
            for result_file in sorted(approach_dir.glob(f"results-{approach}-*.json")):
                parsed = parse_result_filename(result_file, approach)
                if parsed is None:
                    continue
                data_source, step = parsed
                # Resolve online self-data keys (e.g. "ohcam.05") back to their data type.
                data_source = approach_types.get(data_source, data_source)
                try:
                    payload = json.loads(result_file.read_text())
                except json.JSONDecodeError:
                    print(f"warning: could not parse JSON, skipping: {result_file}")
                    continue
                if metric not in payload:
                    print(f"warning: metric '{metric}' missing, skipping: {result_file}")
                    continue
                aggregated[(approach, data_source)][step].append(float(payload[metric]))

    return aggregated


def add_zero_series(aggregated: dict[tuple[str, str], dict[int, list[float]]],
                    zeros: list[str], approach_types: dict[str, str], num_iters: int) -> None:
    """Add flat-zero series for approaches that produced no results (e.g. never solved anything).

    Each spec is ``approach`` or ``approach/data``. A bare approach gets one zero series per
    data source already in the plot, so it groups like a real approach in bar charts. The
    resulting series are plotted like any other, stacking by APPROACH_ORDER.
    """
    if not zeros:
        return
    steps = sorted({step for series in aggregated.values() for step in series})
    if not steps:
        raise SystemExit("--zeros needs at least one approach with real results to borrow steps from.")
    present_data_sources = sorted({data_source for _, data_source in aggregated}, key=data_sort_key)

    for spec in zeros:
        approach, _, data_source = spec.partition("/")
        if not approach:
            raise SystemExit(f"--zeros entry must name an approach: {spec!r}")
        if data_source:
            data_sources = [approach_types.get(data_source, data_source)]
        else:
            # OLAM data is OLAM's own; no other approach is ever run on it, so a bare entry
            # must not fabricate an <approach>/olam series.
            data_sources = [data for data in present_data_sources
                            if data != "olam" or approach == "olam"]
        for data in data_sources:
            if (approach, data) in aggregated:
                print(f"warning: --zeros entry has real results, not zeroing: {approach}/{data}")
                continue
            for step in steps:
                aggregated[(approach, data)][step] = [0.0] * num_iters


def print_final_scores(aggregated: dict[tuple[str, str], dict[int, list[float]]],
                       keys: list[tuple[str, str]], metric: str) -> None:
    print(f"Final {metric} scores:")
    for approach, data_source in keys:
        step_to_values = aggregated[(approach, data_source)]
        final_step = max(step_to_values)
        final_mean = float(np.mean(step_to_values[final_step]))
        final_std_dev = float(np.std(step_to_values[final_step]))
        final_count = len(step_to_values[final_step])
        print(f"  {approach}/{data_source}: {final_mean:.4f} +/- {final_std_dev:.4f} "
              f"(step {final_step}, n={final_count})")


def summarize_steps(step_to_values: dict[int, list[float]], num_iters: int) -> tuple[
    list[int], list[float], list[float], list[int],
]:
    """Return synthetic step-0 plus per-step means, std devs, and sample counts."""
    sorted_steps = sorted(step_to_values)
    steps = [0] + sorted_steps
    means = [0.0] + [float(np.mean(step_to_values[s])) for s in sorted_steps]
    std_devs = [0.0] + [float(np.std(step_to_values[s])) for s in sorted_steps]
    counts = [num_iters] + [len(step_to_values[s]) for s in sorted_steps]
    return steps, means, std_devs, counts


def bar_xtick_labels(bar_entries: list[tuple[str, str, float, float]]) -> list[str]:
    """Label each approach once, centered within its contiguous group of bars."""
    labels = [""] * len(bar_entries)
    group_start = 0
    while group_start < len(bar_entries):
        approach = bar_entries[group_start][0]
        group_end = group_start + 1
        while group_end < len(bar_entries) and bar_entries[group_end][0] == approach:
            group_end += 1
        labels[(group_start + group_end - 1) // 2] = approach_label(approach)
        group_start = group_end
    return labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True,
                        help="Base config JSON (same as passed to eval-learn100.sh).")
    parser.add_argument("--exp-id", type=str, required=True,
                        help="Experiment id prefix; iterations are <exp_id>_1 .. <exp_id>_<num_iters>.")
    parser.add_argument("--num-iters", type=int, required=True, help="Number of iterations to average over.")
    parser.add_argument("--metric", type=str, default=SOLVE_RATE_METRIC,
                        help="Metric key to extract from each results JSON (default: solve rate).")
    parser.add_argument("--output", type=Path, default=None,
                        help="Path to save the plot. Defaults next to the config.")
    parser.add_argument("--jitter", type=float, default=0.001,
                        help="Small per-line vertical offset to separate overlapping lines (plot only).")
    parser.add_argument("--std-dev-shading", action=argparse.BooleanOptionalAction, default=True,
                        help="Shade one standard deviation around each mean line.")
    parser.add_argument("--bar-step", type=int, default=None,
                        help="Plot a bar chart cross section at this step instead of a line chart.")
    parser.add_argument("--noise-step", type=int, default=None,
                        help="Plot success rate vs noise level at this step, over the noise keys "
                             "(ohcam.<level>, conditional-sam.<level>, predicators.<level>) declared "
                             "in the config: one line per (approach, data source).")
    parser.add_argument("--no-legend", action="store_true", default=False,
                        help="Don't make a legend.")
    parser.add_argument("--separate-legend", action=argparse.BooleanOptionalAction, default=True,
                        help="Emit the legend/key as a separate image instead of drawing it on the plot.")
    parser.add_argument("--wide-separate-legend", action=argparse.BooleanOptionalAction, default=True,
                        help="With --separate-legend, emit a single-row legend for a LaTeX figure*: "
                             "the three data sources as line styles, then a color box per approach "
                             "(OLAM last, as its own line, since it uses its own data).")
    parser.add_argument("--legend-font-size", type=float, default=16.0,
                        help="Font size for the separate legend image (default: 16). The legend is "
                             "scaled independently of the panels in LaTeX, so it has its own size.")
    parser.add_argument("--figsize", type=str, default="1.3,1.25",
                        help="Size of the plot box (the axes, not the canvas) as 'width,height' in "
                             "inches. Labels are drawn outside it, so panels with and without "
                             "--hide-ylabel keep identical plot boxes and line up side by side.")
    parser.add_argument("--omit", type=str, nargs="*", default=[],
                        help="List of approaches to omit from the plot.")
    parser.add_argument("--zeros", type=str, nargs="*", default=[],
                        help="Approaches with no results to draw as flat zero lines, e.g. a baseline "
                             "that never solved anything. Each entry is 'approach' (one series per data "
                             "source in the plot) or 'approach/data' for a single series.")
    parser.add_argument("--hide-ylabel", action="store_true",
                        help="Hide the y-axis label and tick numbers (for plots placed side by side).")
    parser.add_argument("--title", type=str, default=None,
                        help="Override the panel title (default: the gt_domain's PDDL domain name). "
                             "A long title widens the tight-bbox canvas, so use a short one in narrow panels.")
    parser.add_argument("--font-scale", type=float, default=0.7,
                        help="Scale all font sizes; sizes are tuned for the default 6x4in figure, "
                             "so use ~0.45 for a small panel in a 6-across row.")
    parser.add_argument("--marker-size", type=float, default=DEFAULT_MARKER_SIZE,
                        help="Point marker size; use 0 to draw lines only (default: 6).")
    parser.add_argument("--line-width", type=float, default=1.5,
                        help="Line width for the mean curves (default: 1.5).")
    parser.add_argument("--num-xticks", type=int, default=5,
                        help="Target number of x tick labels (default: 5, e.g. 0/25/50/75/100). "
                             "Matplotlib's default shrinks this on a narrow panel.")
    parser.add_argument("--num-yticks", type=int, default=5,
                        help="Target number of y tick labels (default: 5, e.g. 0/.25/.5/.75/1).")
    parser.add_argument("--pad-inches", type=float, default=0.01,
                        help="White border kept around the tight bounding box (default: 0.01in). "
                             "Matplotlib's own default is 0.1in, which is a lot on a 1in panel.")
    args = parser.parse_args()

    try:
        fig_w, fig_h = (float(x) for x in args.figsize.split(","))
    except ValueError:
        raise SystemExit("--figsize must be 'width,height', e.g. '6,4'.")

    if args.font_scale <= 0:
        raise SystemExit("--font-scale must be positive.")
    if args.num_xticks < 2 or args.num_yticks < 2:
        raise SystemExit("--num-xticks/--num-yticks must be at least 2.")
    title_size = TITLE_SIZE * args.font_scale
    label_size = LABEL_SIZE * args.font_scale
    tick_size = TICK_SIZE * args.font_scale
    legend_size = LEGEND_SIZE * args.font_scale
    markers = marker_kwargs(args.marker_size)
    # Matplotlib's default pads are absolute points, so they stay huge when the fonts
    # shrink. Scale them too, or a small panel is mostly padding.
    label_pad = LABEL_PAD * args.font_scale
    tick_pad = TICK_PAD * args.font_scale
    title_pad = TITLE_PAD * args.font_scale

    if args.num_iters < 1:
        raise SystemExit("--num-iters must be a positive integer.")
    if args.bar_step is not None and args.noise_step is not None:
        raise SystemExit("--bar-step and --noise-step are mutually exclusive.")

    aggregated = collect_results(args.config, args.exp_id, args.num_iters, args.metric, args.omit)
    if not aggregated:
        raise SystemExit("No step-indexed results found to aggregate.")
    zeros = [spec for spec in args.zeros if spec.partition("/")[0] not in args.omit]
    add_zero_series(aggregated, zeros, approach_types_from_config(args.config), args.num_iters)

    config_dir = args.config.parent
    if args.output is not None:
        output = args.output
    elif args.bar_step is not None:
        output = config_dir / f"{args.exp_id}-{args.metric}-bar-step-{args.bar_step:03d}.png"
    elif args.noise_step is not None:
        output = config_dir / f"{args.exp_id}-{args.metric}-by-noise-step-{args.noise_step:03d}.png"
    else:
        output = config_dir / f"{args.exp_id}-{args.metric}-by-step.png"
    csv_path = output.with_suffix(".csv")

    # --figsize is the axes box, not the canvas: the figure is grown by a fixed margin to hold
    # the title/labels, and bbox_inches="tight" crops whatever of that margin goes unused. Sizing
    # the axes as a *fraction* of the canvas instead would make --hide-ylabel (or any font change)
    # silently resize the plot box, so panels meant to sit side by side would not match.
    fig = plt.figure(figsize=(fig_w + MARGIN_W, fig_h + MARGIN_H))
    ax = fig.add_axes([
        MARGIN_LEFT / (fig_w + MARGIN_W),
        MARGIN_BOTTOM / (fig_h + MARGIN_H),
        fig_w / (fig_w + MARGIN_W),
        fig_h / (fig_h + MARGIN_H),
    ])
    rows: list[tuple] = []
    keys = sorted(aggregated.keys(), key=line_sort_key)
    print_final_scores(aggregated, keys, args.metric)
    summaries: dict[tuple[str, str], tuple[list[int], list[float], list[float], list[int]]] = {}
    for approach, data_source in keys:
        step_to_values = aggregated[(approach, data_source)]
        summaries[(approach, data_source)] = summarize_steps(step_to_values, args.num_iters)
        steps, means, _, counts = summaries[(approach, data_source)]
        for step, mean, count in zip(steps, means, counts):
            rows.append((approach, data_source, step, mean, count))

    legend_keys = keys
    if args.noise_step is not None:
        noise_values = noise_values_from_config(args.config)
        if not noise_values:
            raise SystemExit("No noise keys found in config for --noise-step plot.")
        approach_types = approach_types_from_config(args.config)
        noise_keys = sorted(noise_values, key=lambda key: noise_values[key])
        # One curve per (approach type, data source): the per-noise keys of one approach are
        # points along the same curve, so they collapse to the type they route to
        # ("conditional-sam.2" -> "conditional-sam").
        series_keys = sorted(
            {(approach_types.get(approach, approach), data_source)
             for approach, data_source in keys if approach in noise_values},
            key=line_sort_key,
        )
        if not series_keys:
            raise SystemExit(f"No results found at step {args.noise_step} for the noise keys.")
        rows = []
        legend_keys = [key for key in keys if key[0] in noise_values]
        print(f"{args.metric} at step {args.noise_step} by noise:")
        for approach_type, data_source in series_keys:
            color = color_for_approach(approach_type)
            noise_points: list[tuple[float, float, float, int]] = []
            for noise_key in noise_keys:
                if approach_types.get(noise_key, noise_key) != approach_type:
                    continue
                noise = noise_values[noise_key]
                noise_pct = noise * 100
                steps, means, std_devs, counts = summaries.get(
                    (noise_key, data_source), ([], [], [], []))
                if args.noise_step in steps:
                    step_idx = steps.index(args.noise_step)
                    mean = means[step_idx]
                    std_dev = std_devs[step_idx]
                    count = counts[step_idx]
                else:
                    print(f"warning: no results at step {args.noise_step}, "
                          f"skipping: {noise_key}/{data_source}")
                    continue
                noise_points.append((noise_pct, mean, std_dev, count))
                rows.append((noise_key, data_source, args.noise_step, noise_pct, mean, count))
                print(f"  {noise_key}/{data_source} (noise={noise_pct:g}%): "
                      f"{mean:.4f} +/- {std_dev:.4f} (n={count})")
            if not noise_points:
                continue
            noise_points.sort(key=lambda point: point[0])
            noise_pcts = [point[0] for point in noise_points]
            means = [point[1] for point in noise_points]
            std_devs = [point[2] for point in noise_points]
            if args.std_dev_shading:
                ax.fill_between(noise_pcts,
                                [mean - std_dev for mean, std_dev in zip(means, std_devs)],
                                [mean + std_dev for mean, std_dev in zip(means, std_devs)],
                                color=color, alpha=0.15, linewidth=0,
                                zorder=zorder_for_shading(approach_type))
            ax.plot(noise_pcts, means, color=color,
                    linestyle=linestyle_for_data(data_source), linewidth=args.line_width,
                    label=DATA_LABELS.get(data_source, data_source),
                    zorder=zorder_for_line(approach_type), **markers)
        if not rows:
            raise SystemExit(f"No results found at step {args.noise_step} for the noise plot.")
        ax.set_xlabel("noise %", fontsize=label_size, labelpad=label_pad)
    elif args.bar_step is None:
        for line_idx, (approach, data_source) in enumerate(keys):
            steps, means, std_devs, _ = summaries[(approach, data_source)]
            # Center the per-line offset around 0 so jitter does not bias the values.
            offset = (line_idx - (len(keys) - 1) / 2) * args.jitter
            color = color_for_approach(approach)
            linestyle = linestyle_for_data(data_source)
            label = f"{approach}/{data_source}"
            plotted_means = [mean + offset for mean in means]
            if args.std_dev_shading:
                lower = [mean - std_dev for mean, std_dev in zip(plotted_means, std_devs)]
                upper = [mean + std_dev for mean, std_dev in zip(plotted_means, std_devs)]
                ax.fill_between(steps, lower, upper, color=color, alpha=0.15,
                                linewidth=0, zorder=zorder_for_shading(approach))
            ax.plot(steps, plotted_means, color=color, linestyle=linestyle,
                    linewidth=args.line_width, label=label,
                    zorder=zorder_for_line(approach), **markers)
        ax.set_xlabel("step", fontsize=label_size, labelpad=label_pad)
    else:
        bar_entries: list[tuple[str, str, float, float]] = []
        for approach, data_source in keys:
            steps, means, std_devs, _ = summaries[(approach, data_source)]
            if args.bar_step not in steps:
                print(f"warning: step {args.bar_step} missing, skipping: {approach}/{data_source}")
                continue
            step_idx = steps.index(args.bar_step)
            bar_entries.append((approach, data_source, means[step_idx], std_devs[step_idx]))
        if not bar_entries:
            raise SystemExit(f"No results found at step {args.bar_step}.")
        legend_keys = [(approach, data_source) for approach, data_source, _, _ in bar_entries]
        for bar_idx, (approach, data_source, mean, std_dev) in enumerate(bar_entries):
            yerr = std_dev if args.std_dev_shading else None
            ax.bar(bar_idx, mean, color=color_for_approach(approach), edgecolor="black",
                   hatch=hatch_for_data(data_source), linewidth=0.8, yerr=yerr,
                   capsize=4 if args.std_dev_shading else 0)
        ax.set_xticks(range(len(bar_entries)))
        if args.separate_legend:
            ax.set_xticklabels([])
        else:
            ax.set_xticklabels(bar_xtick_labels(bar_entries), rotation=45, ha="right")
        ax.set_xlabel("approach", fontsize=label_size, labelpad=label_pad)
    if args.hide_ylabel:
        ax.tick_params(axis="y", labelleft=False)
    else:
        ax.set_ylabel("completion rate", fontsize=label_size, labelpad=label_pad)
    title = args.title if args.title is not None else get_gt_domain_name(args.config)
    if args.bar_step is not None or args.noise_step is not None:
        step = args.bar_step if args.bar_step is not None else args.noise_step
        title = f"{title} ({step} steps)"
    ax.set_title(title, fontsize=title_size, pad=title_pad)
    ax.tick_params(labelsize=tick_size, pad=tick_pad,
                   length=TICK_LENGTH * args.font_scale, width=TICK_WIDTH * args.font_scale)
    # AutoLocator picks its tick count from the axis's pixel length, so a narrow panel
    # silently degrades to 0/50/100. Pin the count and allow quarter steps (…/25/…).
    # Ticks are computed over the *data* range: a locator on the axis would have to cover
    # the padded view too, which pushes it back up to the coarser step.
    if args.bar_step is None:
        x_lo, x_hi = ax.dataLim.intervalx
        ax.set_xticks(nice_ticks(x_lo, x_hi, args.num_xticks))
    if args.metric == SOLVE_RATE_METRIC:
        ax.set_yticks(nice_ticks(0.0, 1.0, args.num_yticks))
        ax.set_ylim(-0.02, 1.02)
    else:
        y_lo, y_hi = ax.dataLim.intervaly
        ax.set_yticks(nice_ticks(y_lo, y_hi, args.num_yticks))
    ax.grid(True, alpha=0.3)

    if not args.no_legend:
        if args.separate_legend and args.noise_step is None:
            legend_path = output.with_name(f"{output.stem}-legend{output.suffix}")
            if args.wide_separate_legend:
                # One row, so the legend sits above the panel row in a figure*. The canvas is left
                # generous and bbox_inches="tight" crops it to the entries.
                handles, labels = make_wide_legend(legend_keys, marker_size=args.marker_size)
                legend_fig = plt.figure(figsize=(12.0, 0.8))
                # A short handle renders "-." as a solid line, making the data sources
                # indistinguishable; the dash patterns need room.
                legend_fig.legend(handles, labels, loc="center", ncol=len(labels),
                                fontsize=args.legend_font_size, frameon=False,
                                handlelength=2.4, handleheight=1.0,
                                columnspacing=1.0, handletextpad=0.4)
            else:
                handles, labels = make_legend(legend_keys, bar_chart=args.bar_step is not None,
                                            marker_size=args.marker_size)
                legend_kwargs = {"handlelength": 1.0, "handleheight": 1.0} if args.bar_step is not None else {}
                legend_fig = plt.figure(figsize=(3.5, 0.4 * len(labels) + 0.5))
                legend_fig.legend(handles, labels, loc="center", fontsize=args.legend_font_size,
                                frameon=False, **legend_kwargs)
            legend_fig.savefig(legend_path, dpi=150, bbox_inches="tight", pad_inches=args.pad_inches)
            plt.close(legend_fig)
            print(f"Wrote legend to {legend_path}")
        elif args.noise_step is not None:
            handles, labels = make_noise_step_legend(series_keys, marker_size=args.marker_size)
            ax.legend(handles, labels, loc="upper right", fontsize=legend_size)
        else:
            handles, labels = make_legend(legend_keys, bar_chart=args.bar_step is not None,
                                        marker_size=args.marker_size)
            legend_kwargs = {"handlelength": 1.0, "handleheight": 1.0} if args.bar_step is not None else {}
            ax.legend(handles, labels, bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=legend_size,
                    **legend_kwargs)

    fig.savefig(output, dpi=150, bbox_inches="tight", pad_inches=args.pad_inches)
    print(f"Wrote plot to {output}")

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        if args.noise_step is not None:
            writer.writerow(["approach", "data", "step", "noise_pct", f"mean_{args.metric}", "n_iters"])
        else:
            writer.writerow(["approach", "data", "step", f"mean_{args.metric}", "n_iters"])
        writer.writerows(rows)
    print(f"Wrote aggregated CSV to {csv_path}")


if __name__ == "__main__":
    main()
