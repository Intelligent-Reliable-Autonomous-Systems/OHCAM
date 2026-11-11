

import argparse
from contextlib import redirect_stdout, redirect_stderr
import sys
import os


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--create", action='store_true', default=False, help="Create the experiment directory if it doesn't exist")
    parser.add_argument("--experiment-id", type=str, required=False, default=None, help="Experiment ID to use for the experiment")
    parser.add_argument("--trial-index", type=int, required=False, default=0, help="Trial index to use for the experiment")
    args = parser.parse_args()

    with open(os.devnull, 'w') as devnull:
        with redirect_stdout(devnull), redirect_stderr(devnull):
            from ohcam.dataset import ExperimentDataset
            dataset = ExperimentDataset(args.config, experiment_id=args.experiment_id, trial_index=args.trial_index)
    if args.create:
        print(dataset.experiment_config_path)
        sys.exit()
    problems_with_gt = dataset.get_problems(dataset.interaction_domain_file, mode="train")
    for problem in problems_with_gt:
        print(problem.name)