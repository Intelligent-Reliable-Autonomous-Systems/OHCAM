


import os
import tempfile
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import OneshotPlanner, SequentialSimulator, get_environment
from unified_planning.engines import PlanGenerationResultStatus
from unified_planning.model import MinimizeSequentialPlanLength, Problem
from unified_planning.shortcuts import Compiler
from unified_planning.engines import CompilationKind

get_environment().credits_stream = None

class FDPlanner:

    def __init__(self):
        self.status = None

    def plan(self, problem: Problem, timeout: int = 60):
        self._problem = problem
        problem.add_quality_metric(MinimizeSequentialPlanLength())

        prev_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)          # safe: this is our own process
            with Compiler(
                problem_kind=problem.kind,
                compilation_kind=CompilationKind.STATE_INVARIANTS_REMOVING,
            ) as compiler:
                compiled = compiler.compile(problem)

                with OneshotPlanner(name="fast-downward", problem_kind=compiled.problem.kind) as planner:
                    result = planner.solve(compiled.problem, timeout=timeout)
                self.status = result.status
                if result.status not in (PlanGenerationResultStatus.SOLVED_SATISFICING, PlanGenerationResultStatus.SOLVED_OPTIMALLY):
                    os.chdir(prev_dir)
                    return None

            os.chdir(prev_dir)
            return result.plan.replace_action_instances(
                compiled.map_back_action_instance
            ).actions

    def get_plan_states(self, problem: Problem, plan: list[ActionInstance]):
        with Compiler(
            problem_kind=problem.kind,
            compilation_kind=CompilationKind.STATE_INVARIANTS_REMOVING,
        ) as compiler:
            compiled = compiler.compile(problem)
        with SequentialSimulator(compiled.problem) as simulator:
            state = simulator.get_initial_state()
            states = [state]
            if plan is None:
                return states
            for action in plan:
                compiled_action = compiled.problem.action(action.action.name)(*action.actual_parameters)
                state = simulator.apply(state, compiled_action)
                states.append(state)
            return states