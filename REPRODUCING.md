# Running the paper's experiment protocols

This guide covers running the experiment protocols from the paper on the included domains. For
installation and basic usage, see the [README](README.md).

Each protocol has three steps, run in order: learn, evaluate, then plot. The scripts run several
independent trials of one domain, named `<exp-id>_1`, `<exp-id>_2` and so on. Trial `i` uses
`--trial-index i-1`, so it learns from `problems/train<i-1>` with its own seed. Learning and
evaluating are slow, so the run and evaluation scripts take one domain at a time and can be launched
in parallel. Evaluation results are cached by model, so re-running only evaluates what changed.

In the commands below, `<domain>` is one of the paper's benchmarks: `briefcase`, `citycar`,
`maintenance`, `miconic`, `nurikabe` and `satellite`. Their configs include the expert traces the
offline methods also learn from (`--data train`). Plots are written to `results/<exp-id>/`.

## Sample efficiency

Every approach learns with a budget of 100 steps. Models are saved every 10 steps, and each of
these checkpoints is evaluated.

```bash
# for each <domain>:
bash scripts/run-learn100.sh domains/<domain>/experiment.json run1 5
bash scripts/eval-learn100-step.sh domains/<domain>/experiment.json run1 5 60

# once all domains are evaluated:
bash scripts/plot-learn100.sh run1 5
```

The last argument to the evaluation script is the planner's time limit per problem, in seconds.
`plot-learn100.sh` also prints the fraction of evaluation problems solved.

`scripts/eval-learn100.sh` evaluates only the final models. Its results are not used by the plots.

## Noise scaling

OHCAM, Conditional-SAM and Cluster&Intersect learn at noise levels from 5% to 40%, with 250 steps.
Each level runs under its own approach key, `<approach>.<level>`: for example `ohcam.1` for 10%.
`scripts/run-noise.sh` lists the levels it runs, so the config needs one entry per approach and
level. For OHCAM, set the expected noise ε to the level:

```json
"ohcam.1": {"approach": "ohcam", "online": true, "obs_noise": 0.05, "config": {"noise": 0.1}},
"conditional-sam.1": {"approach": "conditional-sam", "obs_noise": 0.05},
"predicators.1": {"approach": "predicators", "obs_noise": 0.05}
```

The paper set `obs_noise`, the chance of flipping each observed fluent, to half the level, since a
transition is observed through two states. Keep the domain's other `conditional-sam` settings in
each `conditional-sam.<level>` entry.

```bash
# for each <domain>, with a config at domains/<domain>/noise-scale/experiment.json:
bash scripts/run-noise.sh domains/<domain>/noise-scale/experiment.json noise1 5
bash scripts/eval-noise.sh domains/<domain>/noise-scale/experiment.json noise1 5 60

# once all domains are evaluated:
bash scripts/plot-noise.sh noise1 5 noise-scale
```

## Mapping Algorithm 1 to the code

The learner is in [`ohcam/core/`](ohcam/core/). The experiment loop is `run_online_agent` in
[`ohcam/baselines/online/online_agent.py`](ohcam/baselines/online/online_agent.py), and
`OHCAMAgent` adapts the learner to it.

| Alg. 1 line | Code | File in `ohcam/core/` |
| --- | --- | --- |
| 1: initialize hypothesis sets | `OHCAMHypothesisSet.__init__`, `build_action_vocabulary`, `ConditionHypothesisFactory` | `learner.py`, `action_model.py`, `condition_hypothesis.py` |
| 2: reset environment | `InteractionDomain.reset` (`ohcam/env.py`) | |
| 3: interaction budget loop | `run_online_agent` | |
| 4–11: belief-guided exploration | `step_ohcam`, `select_action_monte_carlo` | `learner.py` |
| 6: sample a model | `sample_model_action`, `ConditionHypothesisSet.sample` | `learner.py`, `condition_hypothesis.py` |
| 8: score candidate actions | `sample_action`, `get_bald_utility`, `softmax` | `learner.py`, `utils.py` |
| 9: imagine the transition | `Action.apply` | `action_model.py` |
| 10: rollout utility (Eq. 5) | `transition_log_likelihood`, end of `select_action_monte_carlo` | `learner.py` |
| 12: record the transition | `learn_ohcam_step`, `OHCAMHypothesisSet.update` | `learner.py` |
| 13–15: quantified effects | `QuantifiedHypothesisSet`, `QuantifiedChain`, `iter_param_chains` | `quantified_hypothesis.py`, `quantified_chain.py` |
| 17: belief update (Eq. 1) | `update_beliefs`, `_update_hypotheses`, `normalize` | `condition_hypothesis.py` |
| 18: active bound | `_top_n_log_threshold` | `condition_hypothesis.py` |
| 19–20: branch-and-bound expansion | `try_expand`, `_refinement_log_bound`, `_expand_condition` | `condition_hypothesis.py` |
| 21: return the MAP model | `get_best_model_action`, `get_best_conditions`, `get_best_up_model` | `learner.py`, `condition_hypothesis.py` |

The myopic variant in the paper is the same procedure with `mc_horizon: 1`. The paper's
hyperparameter symbols are noted next to each setting in
[`ohcam/core/config.py`](ohcam/core/config.py).
