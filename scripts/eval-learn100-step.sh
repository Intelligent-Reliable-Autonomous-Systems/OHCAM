#!/bin/bash
#
# Step 2 of the 100-step experiment pipeline: score every 10-step checkpoint learned in step 1.
# These per-step results are what plot-learn100.sh reads.
#
#   1. bash scripts/run-learn100.sh       <config> <exp-id> <num-iters>
#   2. bash scripts/eval-learn100-step.sh <config> <exp-id> <num-iters> <timeout>  # <- this one
#   3. bash scripts/plot-learn100.sh      <exp-id> <num-iters> [nested_dir]
#
# The step loop is outermost and every trial is evaluated at a step before any trial moves to the
# next one, so an interrupted run leaves every trial at the same depth. Results are cached by
# model, so re-running only evaluates what changed.

usage() {
    echo "Usage: ${BASH_SOURCE[0]} <config_file> <experiment_id> <num_iters> <timeout>" >&2
}

eval_learn100_step_main() {
    trap 'status=$?; echo "eval-learn100-step.sh failed on line $LINENO: $BASH_COMMAND (exit $status)" >&2' ERR

    if [[ $# -ne 4 ]]; then
        usage
        return 1
    fi

    local this_dir
    local project_root
    local config_file
    local exp_id
    local num_iters
    local timeout
    this_dir=$(dirname "$(realpath "${BASH_SOURCE[0]}")")
    project_root=$(dirname "$this_dir")
    config_file=$1
    exp_id=$2
    num_iters=$3
    timeout=$4

    cd "$project_root"

    if [[ ! -f "$config_file" ]]; then
        echo "Config file does not exist: $config_file" >&2
        return 1
    fi

    if [[ -z "$exp_id" ]]; then
        echo "Experiment ID must be non-empty." >&2
        return 1
    fi

    if [[ ! "$num_iters" =~ ^[1-9][0-9]*$ ]]; then
        echo "num_iters must be a positive integer." >&2
        return 1
    fi

    if [[ ! "$timeout" =~ ^[1-9][0-9]*$ ]]; then
        echo "timeout must be a positive integer." >&2
        return 1
    fi
    local experiment_config
    local iter
    local iter_exp_id
    local step
    local max_steps=100
    local checkpoint_freq=10
    # Every checkpoint run-learn100.sh writes (10..100 by checkpoint_freq), but coarse first:
    # the ends, then the midpoints, so a run stopped early still spans the whole x axis instead
    # of a prefix of it.
    local steps=(100 50 20 70 30 80 10 90 40 60)
    local experiment_configs=()

    for ((iter = 1; iter <= num_iters; iter++)); do
        iter_exp_id="${exp_id}_${iter}"
        experiment_config=$(python -m ohcam.baselines.experiments \
            --config "$config_file" \
            --create \
            --experiment-id "$iter_exp_id" \
            --trial-index $((iter - 1)))
        echo "Evaluating experiment config [$iter/$num_iters]: $experiment_config"
        experiment_configs+=("$experiment_config")
    done

    for step in "${steps[@]}"; do
        for experiment_config in "${experiment_configs[@]}"; do
            echo "Evaluating step $step/$max_steps: $experiment_config"

            # random data
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach conditional-sam \
                --data random \
                --step "$step" \
                --timeout "$timeout"
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach predicators \
                --data random \
                --step "$step" \
                --timeout "$timeout"
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach ohcam \
                --data random \
                --step "$step" \
                --timeout "$timeout"

            # expert data
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach conditional-sam \
                --data train \
                --step "$step" \
                --timeout "$timeout"
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach predicators \
                --data train \
                --step "$step" \
                --timeout "$timeout"
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach ohcam \
                --data train \
                --step "$step" \
                --timeout "$timeout"

            # ohcam data
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach ohcam \
                --data ohcam \
                --step "$step" \
                --timeout "$timeout"
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach conditional-sam \
                --data ohcam \
                --step "$step" \
                --timeout "$timeout"
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach predicators \
                --data ohcam \
                --step "$step" \
                --timeout "$timeout"

            # olam
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach olam \
                --data olam \
                --step "$step" \
                --timeout "$timeout"
        done
    done
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    (eval_learn100_step_main "$@")
else
    eval_learn100_step_main "$@"
fi
