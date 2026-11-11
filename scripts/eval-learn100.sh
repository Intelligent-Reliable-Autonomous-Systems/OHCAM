#!/bin/bash
#
# Score the final model of every (approach, data) pair learned by run-learn100.sh. This does not
# evaluate the per-step checkpoints, so for the plots in plot-learn100.sh use eval-learn100-step.sh.
# Results are cached by model, so re-running only evaluates what changed.
#
# <timeout> is the per-problem planner budget in seconds.

usage() {
    echo "Usage: ${BASH_SOURCE[0]} <config_file> <experiment_id> <num_iters> <timeout>" >&2
}

eval_learn100_main() {
    trap 'status=$?; echo "eval-learn100.sh failed on line $LINENO: $BASH_COMMAND (exit $status)" >&2' ERR

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

    for ((iter = 1; iter <= num_iters; iter++)); do
        iter_exp_id="${exp_id}_${iter}"
        experiment_config=$(python -m ohcam.baselines.experiments \
            --config "$config_file" \
            --create \
            --experiment-id "$iter_exp_id" \
            --trial-index $((iter - 1)))
        echo "Evaluating experiment config [$iter/$num_iters]: $experiment_config"

        # random data
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach conditional-sam \
            --data random \
            --timeout "$timeout"
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach predicators \
            --data random \
            --timeout "$timeout"
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach ohcam \
            --data random \
            --timeout "$timeout"

        # expert data
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach conditional-sam \
            --data train \
            --timeout "$timeout"
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach predicators \
            --data train \
            --timeout "$timeout"
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach ohcam \
            --data train \
            --timeout "$timeout"

        # ohcam data
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach ohcam \
            --data ohcam \
            --timeout "$timeout"
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach conditional-sam \
            --data ohcam \
            --timeout "$timeout"
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach predicators \
            --data ohcam \
            --timeout "$timeout"

        # olam
        python -m ohcam.metrics.eval \
            --config "$experiment_config" \
            --approach olam \
            --data olam \
            --timeout "$timeout"
    done
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    (eval_learn100_main "$@")
else
    eval_learn100_main "$@"
fi
