#!/bin/bash
#
# Step 2 for the noise figure: score every domain learned in step 1. Evaluates the final model of
# each noise key (no --step), which is the cross section the figure reports; results are cached by
# domain-file hash, so re-running only evaluates what changed.
#
#   1. bash scripts/run-noise.sh  <config> <exp-id> <num-iters>
#   2. bash scripts/eval-noise.sh <config> <exp-id> <num-iters> <timeout>  # <- this script
#   3. bash scripts/plot-noise.sh <exp-id> <num-iters> [nested_dir]
#
# Same <config> <exp-id> <num-iters> as step 1; <timeout> is the per-problem planner budget in
# seconds. The noise levels and the (approach, data) pairs mirror run-noise.sh exactly: whatever
# it learns is what this scores.

usage() {
    echo "Usage: ${BASH_SOURCE[0]} <config_file> <experiment_id> <num_iters> <timeout>" >&2
}

eval_noise_main() {
    trap 'status=$?; echo "eval-noise.sh failed on line $LINENO: $BASH_COMMAND (exit $status)" >&2' ERR

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

    local expert_key="train"
    local experiment_config
    local iter
    local iter_exp_id
    local noise
    # The levels run-noise.sh learns. The loop variable is kept separate from the array, so the
    # array survives the first trial.
    local noise_levels=(".05" ".1" ".15" ".2" ".25" ".3" ".35" ".4")

    for ((iter = 1; iter <= num_iters; iter++)); do
        iter_exp_id="${exp_id}_${iter}"
        experiment_config=$(python -m ohcam.baselines.experiments \
            --config "$config_file" \
            --create \
            --experiment-id "$iter_exp_id" \
            --trial-index $((iter - 1)))
        echo "Evaluating experiment config [$iter/$num_iters]: $experiment_config"

        for noise in "${noise_levels[@]}"; do
            # expert data
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach conditional-sam${noise} \
                --data $expert_key \
                --timeout "$timeout"
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach predicators${noise} \
                --data $expert_key \
                --timeout "$timeout"
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach ohcam${noise} \
                --data $expert_key \
                --timeout "$timeout"

            # ohcam online: the online run logs its traces under its own key
            python -m ohcam.metrics.eval \
                --config "$experiment_config" \
                --approach ohcam${noise} \
                --data ohcam${noise} \
                --timeout "$timeout"
        done

    done
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    (eval_noise_main "$@")
else
    eval_noise_main "$@"
fi
