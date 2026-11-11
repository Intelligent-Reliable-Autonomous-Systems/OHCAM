#!/bin/bash
#
# Step 1 of the experiment pipeline: learn a domain with every approach, over num_iters
# independent trials. Creates <config_dir>/<experiment_id>_<i>/ per trial and writes the
# learned domains, checkpoints and traces there.
#
#   1. bash scripts/run-learn100.sh   <config> <exp-id> <num-iters>           # <- this script
#   2. bash scripts/eval-learn100-step.sh <config> <exp-id> <num-iters> <timeout>
#   3. bash scripts/plot-learn100.sh  <exp-id> <num-iters> [nested_dir]
#

usage() {
    echo "Usage: ${BASH_SOURCE[0]} <config_file> <experiment_id> <num_iters>" >&2
}

run_learn100_main() {
    trap 'status=$?; echo "run-learn100.sh failed on line $LINENO: $BASH_COMMAND (exit $status)" >&2' ERR

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
    local experiment_config
    local experiment_config_paths=""
    local iter
    local iter_exp_id
    local max_steps=100
    local checkpoint_freq=10

    for ((iter = 1; iter <= num_iters; iter++)); do
        iter_exp_id="${exp_id}_${iter}"
        experiment_config=$(python -m ohcam.baselines.experiments \
            --config "$config_file" \
            --create \
            --experiment-id "$iter_exp_id" \
            --trial-index $((iter - 1)))
        experiment_config_paths+="${experiment_config}"$'\n'
        echo "Experiment config [$iter/$num_iters]: $experiment_config"

        # random data
        python -m ohcam.baselines.online.online_agent \
            --config "$experiment_config" \
            --approach random \
            --num-steps "$max_steps" \
            --checkpoint-frequency "$checkpoint_freq"
        python -m ohcam.baselines.offline.offline_agent \
            --config "$experiment_config" \
            --approach conditional-sam \
            --data random \
            --max-steps "$max_steps" \
            --checkpoint-freq "$checkpoint_freq"
        python -m ohcam.baselines.offline.offline_agent \
            --config "$experiment_config" \
            --approach predicators \
            --data random \
            --max-steps "$max_steps" \
            --checkpoint-freq "$checkpoint_freq"
        python -m ohcam.baselines.offline.offline_agent \
            --config "$experiment_config" \
            --approach ohcam \
            --data random \
            --max-steps "$max_steps" \
            --checkpoint-freq "$checkpoint_freq"

        # expert data
        python -m ohcam.baselines.offline.offline_agent \
            --config "$experiment_config" \
            --approach conditional-sam \
            --data train \
            --max-steps "$max_steps" \
            --checkpoint-freq "$checkpoint_freq"
        python -m ohcam.baselines.offline.offline_agent \
            --config "$experiment_config" \
            --approach predicators \
            --data train \
            --max-steps "$max_steps" \
            --checkpoint-freq "$checkpoint_freq"
        python -m ohcam.baselines.offline.offline_agent \
            --config "$experiment_config" \
            --approach ohcam \
            --data train \
            --max-steps "$max_steps" \
            --checkpoint-freq "$checkpoint_freq"

        # ohcam data
        python -m ohcam.baselines.online.online_agent \
            --config "$experiment_config" \
            --approach ohcam \
            --num-steps "$max_steps" \
            --checkpoint-frequency "$checkpoint_freq"
        python -m ohcam.baselines.offline.offline_agent \
            --config "$experiment_config" \
            --approach conditional-sam \
            --data ohcam \
            --max-steps "$max_steps" \
            --checkpoint-freq "$checkpoint_freq"
        python -m ohcam.baselines.offline.offline_agent \
            --config "$experiment_config" \
            --approach predicators \
            --data ohcam \
            --max-steps "$max_steps" \
            --checkpoint-freq "$checkpoint_freq"

        # olam
        python -m ohcam.baselines.online.online_agent \
            --config "$experiment_config" \
            --approach olam \
            --num-steps "$max_steps" \
            --checkpoint-frequency "$checkpoint_freq"

    done

    echo "Experiment config files:"
    printf '%s' "$experiment_config_paths"
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    (run_learn100_main "$@")
else
    run_learn100_main "$@"
fi