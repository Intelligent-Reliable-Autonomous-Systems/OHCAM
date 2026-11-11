#!/bin/bash
#
# Step 1 for the noise figure: learn a domain at every noise level, over num_iters independent
# trials. Creates <config_dir>/<experiment_id>_<i>/ per trial and writes the learned domains,
# checkpoints and traces there.
#
#   1. bash scripts/run-noise.sh   <config> <exp-id> <num-iters>            # <- this script
#   2. bash scripts/eval-noise.sh  <config> <exp-id> <num-iters> <timeout>
#   3. bash scripts/plot-noise.sh  <exp-id> <num-iters> [nested_dir]
#
# The config must declare the <approach>.<level> keys this script learns (see REPRODUCING.md).
#

usage() {
    echo "Usage: ${BASH_SOURCE[0]} <config_file> <experiment_id> <num_iters>" >&2
}

run_noise_main() {
    set -Eeuo pipefail
    trap 'status=$?; echo "run-noise.sh failed on line $LINENO: $BASH_COMMAND (exit $status)" >&2' ERR

    if [[ $# -ne 3 ]]; then
        usage
        return 1
    fi

    local this_dir
    local project_root
    local config_file
    local exp_id
    local num_iters
    this_dir=$(dirname "$(realpath "${BASH_SOURCE[0]}")")
    project_root=$(dirname "$this_dir")
    config_file=$1
    exp_id=$2
    num_iters=$3

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

    local expert_key="train"
    local experiment_config
    local experiment_config_paths=""
    local iter
    local iter_exp_id
    local max_steps=100
    local checkpoint_freq=10
    local noise_levels=(".05" ".1" ".15" ".2" ".25" ".3" ".35" ".4")

    for ((iter = 1; iter <= num_iters; iter++)); do
        iter_exp_id="${exp_id}_${iter}"
        experiment_config=$(python -m ohcam.baselines.experiments \
            --config "$config_file" \
            --create \
            --experiment-id "$iter_exp_id" \
            --trial-index $((iter - 1)))
        experiment_config_paths+="${experiment_config}"$'\n'
        echo "Experiment config [$iter/$num_iters]: $experiment_config"

        for noise in "${noise_levels[@]}"; do
            # expert data
            python -m ohcam.baselines.offline.offline_agent \
                --config "$experiment_config" \
                --approach conditional-sam${noise} \
                --data $expert_key \
                --max-steps "$max_steps"
            python -m ohcam.baselines.offline.offline_agent \
                --config "$experiment_config" \
                --approach predicators${noise} \
                --data $expert_key \
                --max-steps "$max_steps"
            python -m ohcam.baselines.offline.offline_agent \
                --config "$experiment_config" \
                --approach ohcam${noise} \
                --data $expert_key \
                --max-steps "$max_steps"

            # ohcam online
            python -m ohcam.baselines.online.online_agent \
                --config "$experiment_config" \
                --approach ohcam${noise} \
                --num-steps "$max_steps"
        done

    done

    echo "Experiment config files:"
    printf '%s' "$experiment_config_paths"
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    (run_noise_main "$@")
else
    run_noise_main "$@"
fi