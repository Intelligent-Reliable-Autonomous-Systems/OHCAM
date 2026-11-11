import numpy as np

from ohcam.core.condition_hypothesis import ConditionHypothesisSet
from ohcam.core.config import OHCAMConfig
from ohcam.core.pddl_repr import DNF, Condition, Conjunction
from ohcam.core.quantified_chain import QuantifiedChain

NULL_COMPLEXITY: float = 1.0
UNCONDITIONAL_COMPLEXITY: float = 0.5

def get_condition_log_complexity(condition: Condition) -> float:
    if condition.antecedent is False:
        return NULL_COMPLEXITY
    if condition.antecedent is True:
        return UNCONDITIONAL_COMPLEXITY
    if isinstance(condition.antecedent, DNF):
        return sum(np.log(OHCAMConfig.instance().prior_decay) * len(conjunction) for conjunction in condition.antecedent)
    if isinstance(condition.antecedent, Conjunction):
        return np.log(OHCAMConfig.instance().prior_decay) * len(condition.antecedent)
    raise ValueError(f"Invalid antecedent: {condition.antecedent}")

def get_uqv_log_complexity(uqvs: int) -> float:
    return np.log(OHCAMConfig.instance().prior_decay) * uqvs

def get_disjunction_log_complexity(disjunction: frozenset[tuple[QuantifiedChain, ConditionHypothesisSet, int]]) -> float:
    uqv_complexity = sum(get_uqv_log_complexity(len(chain.uqvs)) for chain, _, _ in disjunction)
    condition_complexity = sum(get_condition_log_complexity(hset.get_condition_by_index(condition_idx)) for _, hset, condition_idx in disjunction)
    return uqv_complexity + condition_complexity