from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import random
from typing import Any, Iterator, Literal

import numpy as np
from unified_planning.io import PDDLReader, PDDLWriter
from unified_planning.model import Problem

from ohcam.env import InteractionDomain, TraceLoggerWrapper
from ohcam.up_utils import functional_hash, get_pddl_writer
from ohcam.trace import PDDLPlanParser, Trace



class ExperimentLayout:
    def __init__(self, root_dir: Path, domain_id: str, approach_specs: dict[str, dict[str, Any]], create: bool = False):
        self.root_dir = root_dir
        self.domain_id = domain_id
        self.approach_specs = approach_specs
        if create:
            self.root_dir.mkdir(parents=True, exist_ok=True)
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Experiment directory does not exist: {self.root_dir}")

        self.approach_dirs: dict[str, Path] = {}
        for key in self.approach_specs:
            self.approach_dirs[key] = self.root_dir / key

    def _get_approach_dir(self, approach_name: str, create: bool = True) -> Path:
        if approach_name not in self.approach_dirs:
            raise KeyError(f"Unknown approach: {approach_name}")
        approach_dir = self.approach_dirs[approach_name]
        if create:
            approach_dir.mkdir(parents=True, exist_ok=True)
        return approach_dir

    def get_trace_dir(self, approach_name: str) -> Path:
        approach_dir = self._get_approach_dir(approach_name, create=True)
        spec = self.approach_specs.get(approach_name, {})
        if spec.get("online", False):
            trace_dir = approach_dir / "traces"
        else:
            trace_dir = approach_dir
        trace_dir.mkdir(parents=True, exist_ok=True)
        return trace_dir

    def get_models_dir(self, approach_name: str, data: str) -> Path:
        approach_dir = self._get_approach_dir(approach_name, create=True)
        models_dir = approach_dir / f"models-{data}"
        models_dir.mkdir(parents=True, exist_ok=True)
        return models_dir

    def get_domain_output_path(self, approach_name: str, data_source: str | None = None) -> Path:
        approach_dir = self._get_approach_dir(approach_name, create=True)
        suffix = f"-{data_source}" if data_source else ""
        filename = f"{self.domain_id}-{approach_name}{suffix}.domain.pddl"
        return approach_dir / filename



class ExperimentDataset:

    def __init__(self, config_path: Path | str, experiment_id: str | None = None, trial_index: int | None = None):
        if config_path in ['briefcase', 'citycar', 'maintenance', 'miconic', 'nurikabe', 'satellite']:
            config_path = f"domains/{config_path}/experiment.json"
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file does not exist: {self.config_path}")

        raw_config = json.loads(self.config_path.read_text())
        if raw_config.get("is_experiment", False):
            self.experiment_config_path = self.config_path
            self.experiment_meta = raw_config
            if "experiment_id" not in raw_config:
                raise ValueError("experiment_id must be provided in experiment config")
            self.experiment_id = raw_config["experiment_id"]
            self.experiment_dir = self.experiment_config_path.parent
            self._config_dir = self.experiment_dir
            self.config = raw_config
            should_create_experiment = False
        else:
            self.experiment_config_path = None
            self.experiment_meta = None
            self._config_dir = self.config_path.parent
            self.config = raw_config
            if "experiment_id" in self.config:
                self.experiment_id = self.config["experiment_id"]
            else:
                experiment_prefix = self.config.get("experiment_prefix", self._default_experiment_prefix())
                self.experiment_id = self._new_experiment_id(prefix=experiment_prefix)
            if experiment_id is not None:
                self.experiment_id = experiment_id
            self.experiment_dir = self._config_dir / self.experiment_id
            should_create_experiment = not self.experiment_dir.exists()

        required = ["initial_domain", "gt_domain", "train_problems", "approaches", "max_steps"]
        for key in required:
            if key not in self.config:
                raise ValueError(f"{key} must be provided in the config file")

        if trial_index is None:
            trial_index = self.config.get("trial_index", 0)
        if trial_index < 0:
            raise ValueError(f"trial_index must be non-negative, got {trial_index}")
        self.trial_index = trial_index

        self.initial_domain_file = self._resolve_path(self._config_dir, self.config["initial_domain"])
        self.gt_domain_file = self._resolve_path(self._config_dir, self.config["gt_domain"])
        self.interaction_domain_file = self.gt_domain_file

        self.problem_files = self._parse_path_list(
            self._select_trial_entry(self.config["train_problems"], "train_problems"), suffix=".pddl")
        self.problem_files_eval = self._parse_path_list(self.config.get("eval_problems", []), suffix=".pddl")
        self.eval_trace_files = self._parse_path_list(self.config.get("eval_traces", []), suffix=".trace")
        self.train_trace_files = self._parse_path_list(
            self._select_trial_entry(self.config.get("train_traces", []), "train_traces"), suffix=".trace")
        self.max_steps = self.config["max_steps"]

        self.domain_id = self._domain_id_from_domain_file(self.gt_domain_file)
        self.cache_dir = self._config_dir / ".." / "eval-cache"

        try:
            self._pddl_reader = PDDLReader()
        except:
            self._pddl_reader = PDDLReader()
        self._gt_domain = self._pddl_reader.parse_problem(str(self.gt_domain_file))
        self.interaction_domain = InteractionDomain(self._gt_domain)
        self.initial_domain = self._pddl_reader.parse_problem(str(self.initial_domain_file))
        self._plan_parser = PDDLPlanParser(self._gt_domain, prefer_delta=True)

        self.approach_specs = self._parse_approaches(self.config.get("approaches", {}))
        self.approaches: dict[str, Path] = {}
        self.experiment: ExperimentLayout | None = None
        self.fixed_preconditions = self.config.get("fixed_preconditions", False)

        if should_create_experiment:
            self.create_experiment(self.experiment_id)
        else:
            if not self.experiment_dir.exists():
                raise FileNotFoundError(
                    f"experiment_id is set to {self.experiment_id}, "
                    f"but directory does not exist: {self.experiment_dir}"
                )
            self.load_experiment(self.experiment_dir)

    def _domain_id_from_domain_file(self, domain_file: Path) -> str:
        name = domain_file.name
        if name.endswith(".domain.pddl"):
            name = name[:-len(".domain.pddl")]
        if name.endswith("-gt"):
            name = name[:-len("-gt")]
        return name

    def _parse_approaches(self, approaches_cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
        specs: dict[str, dict[str, Any]] = {}
        for key, value in approaches_cfg.items():
            if isinstance(value, dict):
                specs[key] = value
            else:
                raise ValueError(f"Invalid approach config for {key}: {value}")
        return specs


    def create_experiment(self, experiment_name: str | None = None) -> Path:
        if experiment_name is None:
            experiment_name = self._new_experiment_id()
        experiment_dir = self._config_dir / experiment_name
        self.experiment = ExperimentLayout(experiment_dir, self.domain_id, self.approach_specs, create=True)
        self.approaches = self.experiment.approach_dirs.copy()
        self.experiment_dir = experiment_dir
        self.experiment_id = experiment_name
        self.experiment_config_path = experiment_dir / "experiment.json"
        experiment_meta = self._build_experiment_config(experiment_dir)
        self.experiment_meta = experiment_meta
        self.experiment_config_path.write_text(json.dumps(experiment_meta, indent=4))
        return experiment_dir

    def load_experiment(self, experiment_dir: Path) -> None:
        self.experiment = ExperimentLayout(experiment_dir, self.domain_id, self.approach_specs, create=False)
        self.experiment_dir = experiment_dir
        self.experiment_config_path = experiment_dir / "experiment.json"
        self.approaches = self.experiment.approach_dirs.copy()



    def _default_experiment_prefix(self) -> str:
        if self._config_dir.parent.name:
            return f"{self._config_dir.parent.name}-{self._config_dir.name}"
        return self._config_dir.name

    def _new_experiment_id(self, prefix: str | None = None) -> str:
        timestamp = datetime.now().strftime("%y-%m-%d-%H%M%S")
        if prefix is None:
            prefix = self._default_experiment_prefix()
        return f"{prefix}-{timestamp}"

    def _build_experiment_config(self, experiment_dir: Path) -> dict[str, Any]:
        experiment_cfg = json.loads(json.dumps(self.config))
        path_keys = ["initial_domain", "gt_domain"]
        list_path_keys = ["train_problems", "eval_problems", "eval_traces", "train_traces"]

        for key in path_keys:
            if key in experiment_cfg:
                src = self._resolve_path(self.config_path.parent, experiment_cfg[key])
                experiment_cfg[key] = self._relativize_path_for_experiment(src, experiment_dir)

        for key in list_path_keys:
            if key not in experiment_cfg:
                continue
            raw_paths = experiment_cfg[key]
            if isinstance(raw_paths, str):
                raw_paths = [raw_paths]
            normalized_paths = []
            for p in raw_paths:
                src = self._resolve_path(self.config_path.parent, p)
                normalized_paths.append(self._relativize_path_for_experiment(src, experiment_dir))
            experiment_cfg[key] = normalized_paths

        experiment_cfg["is_experiment"] = True
        experiment_cfg["experiment_id"] = self.experiment_id
        experiment_cfg["trial_index"] = self.trial_index
        experiment_cfg["parent_config"] = str(Path("..") / self.config_path.name)
        experiment_cfg.pop("experiment_prefix", None)
        return experiment_cfg

    def _relativize_path_for_experiment(self, path: Path, experiment_dir: Path) -> str:
        abs_path = Path(path).resolve()
        rel_path = os.path.relpath(str(abs_path), str(experiment_dir.resolve()))
        return str(Path(rel_path))

    def _select_trial_entry(self, path_list: list[str] | str, key: str) -> list[str]:
        """Pick the entry of a trial-indexed path list belonging to this trial.

        ``train_problems``/``train_traces`` list one path per trial (e.g. train0,
        train1, ...), so a trial only sees its own slice of the data. A list with a
        single entry is shared by every trial, which keeps single-trial configs working.
        """
        if isinstance(path_list, str):
            path_list = [path_list]
        if len(path_list) <= 1:
            return list(path_list)
        if self.trial_index >= len(path_list):
            raise ValueError(
                f"trial_index {self.trial_index} is out of range for {key} "
                f"({len(path_list)} entries in {self.config_path})"
            )
        return [path_list[self.trial_index]]

    def seed_rngs(self) -> int:
        """Seed the global RNGs from the trial index so trials differ but replay identically."""
        seed = self.trial_index
        random.seed(seed)
        np.random.seed(seed)
        return seed

    def _parse_path_list(self, path_list: list[str] | str, suffix: str) -> list[Path]:
        if isinstance(path_list, str):
            path_list = [path_list]
        files_or_dirs = [self._resolve_path(self._config_dir, p) for p in path_list]
        all_files: list[Path] = []
        for path in files_or_dirs:
            if not path.exists():
                raise FileNotFoundError(f"File {path} does not exist")
            if path.is_dir():
                all_files.extend(sorted(path.glob(f"*{suffix}"), key=lambda p: p.name))
            else:
                all_files.append(path)
        return all_files

    def get_obs_noise(self, approach_key: str | None = None, mode: Literal["train", "eval"] = "train") -> float:
        """Resolve the observation noise rate for an approach.

        A per-approach ``obs_noise`` overrides the global one. Eval mode is always noiseless.
        """
        if mode != "train":
            return 0.0
        noise = self.config.get("obs_noise", 0.0)
        if approach_key is not None:
            spec = self.approach_specs.get(approach_key, {})
            if "obs_noise" in spec:
                noise = spec["obs_noise"]
        return noise

    def get_environment(self, approach_to_log_data: str | None = None, dict_obs: bool = False, mode: Literal["train", "eval"] = "train") -> InteractionDomain:
        noise = self.get_obs_noise(approach_to_log_data, mode)
        env = InteractionDomain(self._gt_domain, obs_as_dict=dict_obs, obs_noise=noise)
        if approach_to_log_data is not None:
            env = TraceLoggerWrapper(env, self.experiment.get_trace_dir(approach_to_log_data), meta={
                'approach': approach_to_log_data,
            })
        return env

    def get_approach_cfg(self, approach_name: str) -> dict[str, Any]:
        if approach_name not in self.approach_specs:
            return {} # Default to empty config
        return self.approach_specs[approach_name]

    def get_approach_type(self, approach_key: str) -> str:
        """Return the agent type used to route an approach key to its implementation.

        Approaches may set an explicit ``approach`` field so the same agent can run
        under multiple keys (e.g. ``ohcam.05`` -> ``ohcam``). When absent we fall back
        to the key itself, keeping configs keyed directly by agent name working.
        """
        spec = self.approach_specs.get(approach_key, {})
        return spec.get("approach", approach_key)

    def get_problems(self, domain: Path, mode: Literal["train", "eval"] = "train") -> list[Problem]:
        return list(self.get_problems_iter(domain, mode))

    def get_problems_iter(self, domain: Path, mode: Literal["train", "eval"] = "train") -> Iterator[Problem]:
        if mode == "train":
            problem_files = self.problem_files
        elif mode == "eval":
            problem_files = self.problem_files_eval
        else:
            raise ValueError(f"Invalid mode: {mode}")
        if isinstance(domain, Path):
            domain_str = domain.read_text()
        else:
            raise NotImplementedError("Domain must be a Path") # PDDLWriter is not consistent
        problem_strs = [path.read_text() for path in problem_files]
        problems = [self._pddl_reader.parse_problem_string(domain_str, problem_str) for problem_str in problem_strs]
        return problems



    def get_eval_traces(self) -> list[Trace]:
        traces = []
        for trace_file in self.eval_trace_files:
            if not trace_file.exists():
                raise FileNotFoundError(f"Eval trace file {trace_file} does not exist")
            traces.append(self._plan_parser.parse_trace_file(trace_file))
        return traces

    def get_train_traces(self) -> list[Trace]:
        traces = []
        for trace_file in self.train_trace_files:
            if not trace_file.exists():
                raise FileNotFoundError(f"Train trace file {trace_file} does not exist")
            traces.append(self._plan_parser.parse_trace_file(trace_file))
        return traces



    def _get_trace_files_for_data_source(self, data_source: str) -> list[Path]:
        if data_source == "eval":
            return sorted(self.eval_trace_files)
        if data_source == "train":
            return sorted(self.train_trace_files)
        if data_source not in self.approach_specs:
            raise KeyError(
                f"Unknown data source '{data_source}'. "
                f"Expected one of {sorted(self.approach_specs.keys()) + ['eval']}."
            )
        if self.experiment is None:
            raise ValueError("No experiment loaded; cannot resolve approach trace directories")
        trace_dir = self.experiment.get_trace_dir(data_source)
        return sorted(trace_dir.glob("*.trace"))

    def get_traces(self, data_source: str) -> Iterator[Trace]:
        if data_source == "eval":
            for trace in self.get_eval_traces():
                yield trace
            return
        if data_source == "train":
            for trace in self.get_train_traces():
                yield trace
            return
        trace_files = self._get_trace_files_for_data_source(data_source)
        for trace_file in trace_files:
            if not trace_file.exists():
                raise FileNotFoundError(f"Trace file {trace_file} does not exist")
            yield self._plan_parser.parse_trace_file(trace_file)



    def get_approach_dir(self, approach_name: str) -> Path:
        if approach_name == "ground-truth":
            return self.experiment_dir / "ground-truth"
        if approach_name == "initial":
            return self.experiment_dir / "initial"
        if approach_name not in self.approaches:
            raise KeyError(f"Unknown approach: {approach_name}")
        approach_dir = self.approaches[approach_name]
        approach_dir.mkdir(parents=True, exist_ok=True)
        return approach_dir

    def get_approach_domain_path(self, approach_name: str, data_source: str, step: int | None = None) -> Path:
        """Get the path to the learned domain for an approach.

        If the approach is "ground-truth", return the path to the interaction domain.
        """
        if approach_name == "ground-truth":
            return self.gt_domain_file
        if approach_name == "initial":
            return self.initial_domain_file
        if self.experiment is not None:
            if step is not None:
                models_dir = self.experiment.get_models_dir(approach_name, data_source)
                return models_dir / f"{self.domain_id}-{approach_name}-step-{step:03d}.domain.pddl"
            return self.experiment.get_domain_output_path(approach_name, data_source=data_source)

        if step is not None:
            raise ValueError("Step-indexed model paths require an experiment layout.")
        if approach_name not in self.approaches:
            raise KeyError(f"Unknown approach: {approach_name}")
        return self.get_approach_dir(approach_name) / f"{self.domain_id}-{approach_name}-{data_source}.domain.pddl"

    def get_eval_cache_path(self, domain_path: Path) -> Path:
        """Get the cache path for the eval results of a model, keyed by its meaning.

        Models that differ only in ordering or variable names share an entry (see ``functional_hash``).
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            digest = functional_hash(self._pddl_reader.parse_problem(str(domain_path)))
        except NotImplementedError:
            digest = hashlib.md5(Path(domain_path).read_bytes()).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get_learned_domain(self, approach_name: str, data_source: str, step: int | None = None) -> Problem:
        learned_domain_path = self.get_approach_domain_path(approach_name, data_source=data_source, step=step)
        return self._pddl_reader.parse_problem(str(learned_domain_path))

    def get_pddl_writer(self, up_domain: Problem) -> PDDLWriter:
        return get_pddl_writer(up_domain)

    def _resolve_path(self, base_dir: Path, path_str: str | Path) -> Path:
        path = Path(path_str)
        if path.is_absolute():
            return path
        return (base_dir / path).resolve()

def corrupt_traces_with_noise(traces: list[Trace], obs_noise: float, seed: int = 42) -> list[Trace]:
    """Corrupt trace states in place using the same per-fluent flip used by the env.

    Each fluent in every state is independently flipped with probability ``obs_noise``.
    A fixed ``seed`` keeps the corruption deterministic across trials.
    """
    if obs_noise <= 0:
        return traces
    rng = np.random.RandomState(seed)
    for trace in traces:
        for state in trace.states:
            for fluent in list(state.keys()):
                if rng.random_sample() < obs_noise:
                    state[fluent] = not state[fluent]
    return traces
