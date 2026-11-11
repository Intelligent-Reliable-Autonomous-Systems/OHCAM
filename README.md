# OHCAM: Online Hypothesis-Guided Learning of Conditional Action Models

Preprint: [arXiv:2608.30955](https://arxiv.org/abs/2608.30955)

OHCAM learns a PDDL action model by acting in an environment. You give it an initial model
(for example, the action signatures with empty preconditions and effects) and a simulator of the
true domain, and it learns preconditions and effects, including conditional (`when`) and
universally quantified (`forall`) effects.

At each step, OHCAM keeps a posterior over candidate preconditions and effects for every action,
imagines short rollouts under models sampled from that posterior, and executes the action whose
outcome is most informative. It writes the most likely model as a PDDL domain file.

This repository also includes the baselines from the paper (Conditional-SAM, Cluster&Intersect,
OLAM, LAMP) behind the same interface. To reproduce the paper's experiments, see
[REPRODUCING.md](REPRODUCING.md).

## Installation

Requires Python 3.11 or newer. `requirements.txt` installs the baselines' libraries from
`third_party/`, which holds patched copies of unified-planning, predicators, AMLGym, sam_learning
and pddl_plus_parser. Each one lists its changes from upstream in its `MODIFICATIONS.md`.

```bash
conda create -n ohcam python=3.12
conda activate ohcam
pip install -r requirements.txt
pip install -e .
```

The LAMP baseline also needs [pracmln](https://github.com/danielnyga/pracmln), which is not
included: clone it to `third_party/pracmln` and uncomment the LAMP lines in `requirements.txt`.

Run the commands below from the repository root with the environment active.

## Learn a domain

The included domains are in `domains/`: `briefcase`, `citycar`, `maintenance`, `miconic`,
`nurikabe` and `satellite` (the paper's benchmarks), and `magnetblocks` and `spongeworld`. Each
directory has:

- `experiment.json`, the config;
- the true domain, which the simulator runs;
- the initial domain that learning starts from;
- `problems/`, the training problems (`train0` to `train4`, one set per trial, or a single
  `train`) and the evaluation problems (`eval`);
- `problems/traces/`, expert traces for training and evaluation (benchmark domains only).

**1. Create an experiment.** This makes a directory for its outputs and prints the path of its config:

```bash
CONFIG=$(python -m ohcam.baselines.experiments --config domains/briefcase/experiment.json --create --experiment-id demo)
# CONFIG=domains/briefcase/demo/experiment.json
```

Add `--trial-index 1` (up to 4) to learn from a different training set with a different seed.
In `magnetblocks` and `spongeworld`, every trial shares one training set.

**2. Learn online.** OHCAM interacts with the simulator for the config's `max_steps` steps:

```bash
python -m ohcam.baselines.online.online_agent --config $CONFIG --approach ohcam
```

Add `--num-steps 10` for a quick try. Each step plans for up to 5 seconds by default, so 100
steps take several minutes.

**3. Look at the learned model:**

```bash
cat domains/briefcase/demo/ohcam/briefcaseworld-ohcam-ohcam.domain.pddl
```

**4. Evaluate it (optional).** This plans with the learned model on the evaluation problems and
executes the plans in the true domain:

```bash
python -m ohcam.metrics.eval --config $CONFIG --approach ohcam --data ohcam
```

### Learning offline from traces

OHCAM can also learn from traces. `--data train` uses the expert traces listed in the config's
`train_traces`. `--data <approach>` uses the traces an online approach collected in this
experiment.

```bash
python -m ohcam.baselines.offline.offline_agent --config $CONFIG --approach ohcam --data train
```

The baselines run the same way:


| Method                                             | `--approach`      | Runner            |
| ---------------------------------------------------- | ------------------- | ------------------- |
| OHCAM                                              | `ohcam`           | online or offline |
| Random exploration (collects data, learns nothing) | `random`          | online            |
| OLAM                                               | `olam`            | online            |
| Conditional-SAM                                    | `conditional-sam` | offline           |
| Cluster&Intersect                                  | `predicators`     | offline           |
| LAMP                                               | `lamp`            | offline (slow)    |

For example, to learn with Conditional-SAM from OHCAM's data:

```bash
python -m ohcam.baselines.offline.offline_agent --config $CONFIG --approach conditional-sam --data ohcam
```

## Outputs

Everything goes in the experiment directory, under one subdirectory per approach:


| File                                                     | Contents                                                                  |
| ---------------------------------------------------------- | --------------------------------------------------------------------------- |
| `<domain>-<approach>-<data>.domain.pddl`                 | The final learned model. For online runs,`<data>` is the approach itself. |
| `models-<data>/<domain>-<approach>-step-NNN.domain.pddl` | Models saved during learning.                                             |
| `traces/`                                                | The transitions an online approach observed.                              |
| `statistics-<approach>-<data>.json`                      | Run time, memory, and hypothesis-space statistics.                        |
| `results-<approach>-<data>.json`                         | Evaluation results, written by`ohcam.metrics.eval`.                       |

The evaluation reports three kinds of results:

- `solving`: the fraction of evaluation problems whose plan, made with the learned model, reaches
  the goal in the true domain (`avg-goal-reached`).
- `pred_eff`: precision and recall of predicted effects on the config's `eval_traces`.
- `pred_app`: how well the learned preconditions predict when actions are applicable, also on
  `eval_traces`.

`magnetblocks` and `spongeworld` have no traces, so only `solving` is meaningful for them.

## Using your own domain

You need:

- the true domain, which the simulator runs;
- an initial domain with the same types, predicates and action parameters (preconditions and
  effects may be empty);
- a directory of PDDL problems to interact in.

Then write a config like this one:

```json
{
    "initial_domain": "./mydomain-empty.domain.pddl",
    "gt_domain": "./mydomain.domain.pddl",
    "train_problems": ["./train-problems/"],
    "eval_problems": ["./eval-problems/"],
    "max_steps": 100,
    "approaches": {
        "ohcam": {"online": true, "config": {}}
    }
}
```

Relative paths are resolved from the config's directory.


| Field                         | Meaning                                                                                                                 |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `initial_domain`              | The model learning starts from.                                                                                         |
| `gt_domain`                   | The true domain, used to simulate the environment and to evaluate.                                                      |
| `train_problems`              | Problems (files or directories) to interact in. With several entries, each trial uses the one at its`--trial-index`.    |
| `max_steps`                   | The interaction budget.                                                                                                 |
| `approaches`                  | One entry per approach key (see below).                                                                                 |
| `eval_problems`               | *Optional.* Problems used to evaluate solving.                                                                          |
| `eval_traces`, `train_traces` | *Optional.* Traces used to evaluate predictions (`eval_traces`), and expert traces for `--data train` (`train_traces`). |
| `fixed_preconditions`         | *Optional.* Keep the initial domain's preconditions in every learned model.                                             |
| `obs_noise`                   | *Optional.* The probability of flipping each observed fluent, to simulate noisy perception.                             |

Each entry in `approaches` can set:

- `online`: whether the approach collects its own data.
- `approach`: the method to run, if the key isn't the method name. For example, keys `ohcam.a` and
  `ohcam.b` with `"approach": "ohcam"` run OHCAM twice with different settings.
- `obs_noise`: overrides the top-level `obs_noise` for this approach.
- `config`: OHCAM settings (see below).
- `offline_config`: OHCAM settings used only when learning offline.

The OHCAM settings that matter most are below. All settings are documented in
[`ohcam/core/config.py`](ohcam/core/config.py).


| Setting                       | Default     | Meaning                                                                                      |
| ------------------------------- | ------------- | ---------------------------------------------------------------------------------------------- |
| `noise`                       | `1e-8`      | Expected rate of perception and execution errors (ε in the paper). Raise it for noisy data. |
| `prior_decay`                 | `0.1`       | Prior penalty per condition literal (α).                                                    |
| `hypothesis_expansion_target` | `128`       | Hypotheses kept active per precondition or effect (n).                                       |
| `combine_preconditions`       | `true`      | Return the conjunction of all likely precondition terms, a safe over-approximation.          |
| `mc_rollouts`, `mc_horizon`   | `1000`, `4` | Imagined rollouts per step and their length (N, k).                                          |
| `max_planning_time`           | `5.0`       | Seconds of planning per step.                                                                |

## Code layout


| Path                                                                   | Contents                                                 |
| ------------------------------------------------------------------------ | ---------------------------------------------------------- |
| [`ohcam/core/`](ohcam/core/)                                           | The OHCAM learner.                                       |
| [`ohcam/baselines/`](ohcam/baselines/)                                 | The online and offline runners, and the baseline agents. |
| [`ohcam/metrics/eval.py`](ohcam/metrics/eval.py)                       | Evaluation of learned models.                            |
| [`ohcam/dataset.py`](ohcam/dataset.py), [`ohcam/env.py`](ohcam/env.py) | Experiment configs and the simulated environment.        |
| [`scripts/`](scripts/)                                                 | Scripts for the paper's experiments and figures.         |
