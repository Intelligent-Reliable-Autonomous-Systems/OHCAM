#!/bin/bash
#
# Step 3 for the noise figure: aggregate every domain's noise sweep into a step-250 cross
# section and average those into the paper's noise figure.
#
#   1. bash scripts/run-noise.sh   <config> <exp-id> <num-iters>
#   2. bash scripts/eval-noise.sh  <config> <exp-id> <num-iters> <timeout>
#   3. bash scripts/plot-noise.sh  <exp-id> <num-iters> [nested_dir]      # <- this script
#
# Each domain is aggregated over the ohcam.<level>, conditional-sam.<level> and
# predicators.<level> keys that run-noise.sh runs, into
#
#   results/<exp_id>/<domain_exp_id>-avg-goal-reached-by-noise-step-250.csv
#
# which plot_noise_scale.py then normalizes per domain and averages into noise.pdf.
#
# usage: bash scripts/plot-noise.sh <experiment_id> <num_trials> [nested_directory]

usage() {
    echo "Usage: ${BASH_SOURCE[0]} <experiment_id> <num_trials> [nested_directory]" >&2
}

# A domain uses the passed id when it has a run under it and otherwise falls back to the single
# <id>_1 trial directory it does have. Prints nothing and returns 1 when there is no run, or more
# than one candidate, to pick from.
resolve_exp_id() {
    local config_dir=$1
    local preferred=$2
    local candidates=()
    local candidate

    if [[ -d "$config_dir/${preferred}_1" ]]; then
        echo "$preferred"
        return 0
    fi
    mapfile -t candidates < <(compgen -G "$config_dir/*_1" || true)
    if [[ ${#candidates[@]} -ne 1 ]]; then
        return 1
    fi
    candidate=$(basename "${candidates[0]}")
    echo "${candidate%_1}"
}

plot_noise_main() {
    trap 'status=$?; echo "plot-noise.sh failed on line $LINENO: $BASH_COMMAND (exit $status)" >&2' ERR

    if [[ $# -ne 2 && $# -ne 3 ]]; then
        usage
        return 1
    fi

    local this_dir
    local project_root
    this_dir=$(dirname "$(realpath "${BASH_SOURCE[0]}")")
    project_root=$(dirname "$this_dir")
    cd "$project_root"

    local experiment_id=$1
    local num_trials=$2
    local nested_directory=${3:-noise-scale}

    if [[ ! "$num_trials" =~ ^[1-9][0-9]*$ ]]; then
        echo "num_trials must be a positive integer." >&2
        return 1
    fi

    # Ensure nested_directory ends with '/'
    case "$nested_directory" in
        "") ;;
        */) ;;
        *) nested_directory="${nested_directory}/" ;;
    esac
    local output_dir="results/${experiment_id}"
    local step=250   # the cross section the paper reports
    local row domain title config_file config_dir exp_id csv_path
    local written_csvs=()

    mkdir -p "$output_dir"

    local -a domains=(
        "miconic|Miconic"
        "maintenance|Maintenance"
        "briefcase|Briefcase"
        "citycar|CityCar"
        "nurikabe|Nurikabe"
        "satellite|Satellite"
    )

    echo "=== Noise cross sections at step $step -> $output_dir"
    for row in "${domains[@]}"; do
        IFS='|' read -r domain title <<< "$row"
        config_file="domains/${domain}/${nested_directory}experiment.json"
        config_dir=$(dirname "$config_file")
        echo "--- $title"
        if [[ ! -f "$config_file" ]]; then
            echo "  skipped: no config at $config_file" >&2
            continue
        fi
        if ! exp_id=$(resolve_exp_id "$config_dir" "$experiment_id"); then
            echo "  skipped: no unique <exp-id>_1 run directory in $config_dir" \
                 "(run run-noise.sh and eval-noise.sh on this config first)" >&2
            continue
        fi
        echo "  exp-id: $exp_id"
        python scripts/aggregate_evals.py \
            --config "$config_file" \
            --exp-id "$exp_id" \
            --num-iters "$num_trials" \
            --noise-step "$step" \
            --title "$title" \
            --output "$output_dir/${exp_id}-avg-goal-reached-by-noise-step-${step}.png"
        written_csvs+=("$output_dir/${exp_id}-avg-goal-reached-by-noise-step-${step}.csv")
    done

    # plot_noise_scale.py globs every by-noise CSV in the directory, so one left there by a sweep
    # under a different exp-id would count its domain a second time in the average. Nothing is
    # deleted here: point <experiment_id> at a fresh directory instead.
    for csv_path in "$output_dir"/*-by-noise-step-*.csv; do
        [[ -f "$csv_path" ]] || continue
        if [[ ! " ${written_csvs[*]} " == *" $csv_path "* ]]; then
            echo "warning: $csv_path is not from this run but is averaged in too" >&2
        fi
    done

    echo
    if compgen -G "$output_dir/*-by-noise-step-*.csv" >/dev/null; then
        echo "=== Noise figure, mean over domains -> $output_dir/noise.png"
        python scripts/plot_noise_scale.py \
            --bar \
            --csv-dir "$output_dir" \
            --step "$step" \
            --std-dev-shading \
            --output "$output_dir/noise.png"
    else
        echo "=== Noise figure: skipped, no noise sweeps were aggregated" >&2
        return 1
    fi

    echo
    echo "Outputs in $output_dir:"
    ls -1 "$output_dir"
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    (plot_noise_main "$@")
else
    plot_noise_main "$@"
fi
