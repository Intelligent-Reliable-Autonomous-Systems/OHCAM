# usage: bash scripts/plot-learn100.sh <experiment_name> <num_trials> [nested_directory]

usage() {
    echo "Usage: ${BASH_SOURCE[0]} <experiment_name> <num_trials> [nested_directory]" >&2
    exit 1
}

if [[ $# -ne 2 && $# -ne 3 ]]; then
    usage
    exit 1
fi
experiment_name=$1
num_trials=$2
nested_directory=$3

if [ -z "$nested_directory" ]; then
    nested_directory=""
else
    # Ensure nested_directory ends with '/'
    case "$nested_directory" in
        */) ;;
        *) nested_directory="${nested_directory}/" ;;
    esac
fi

domains=(
    "miconic|Miconic"
    "maintenance|Maintenance"
    "briefcase|Briefcase"
    "citycar|CityCar"
    "nurikabe|Nurikabe"
    "satellite|Satellite"
)

for row in "${domains[@]}"; do
    IFS='|' read -r domain title <<< "$row"
    config_file="domains/${domain}/${nested_directory}experiment.json"
    output_directory="results/${experiment_name}"
    mkdir -p $output_directory
    python scripts/aggregate_evals.py --config $config_file --exp-id ${experiment_name} --num-iters ${num_trials} --title ${title} --output ${output_directory}/${domain}-efficiency.png --hide-ylabel --no-legend
done

