
from collections import OrderedDict
from collections.abc import Sequence
import itertools
from ohcam.core.config import OHCAMConfig
from ohcam.up_utils import FluentExpLike
from unified_planning.model import FNode, Fluent as UPFluent, OperatorKind, Problem, Type as UPType, Parameter as UPParameter, Variable as UPVariable, Object as UPObject
from unified_planning.model import InstantaneousAction as UPAction
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import And, FluentExp, Not, Or, get_environment, Equals

from ohcam.core.pddl_repr import Condition, Outcome, Type, Atom, DisjunctiveAtom, Conjunction, GroundedAtom
from ohcam.core.quantified_chain import QuantifiedChain

class Action:

    def __init__(self,
            name: str,
            parameters: dict[str, Type],
            precondition: Condition | None = None,
            effects: dict[Atom, Condition] = None,
            quantifiers: dict[QuantifiedChain, Condition] = None):
        self.name = name
        self.parameters = parameters
        if precondition and precondition.outcome != Outcome.APPLICABLE:
            raise ValueError(f"Invalid precondition: {precondition}")
        self.precondition = precondition or Condition(True, Outcome.APPLICABLE)
        self.effects: dict[Atom, Condition] = effects or {}
        """A dictionary of effects, mapping each effect atom to its condition that must be satisfied for the effect to be applied.

        Each atom must be action-bound.
        """
        self.quantifiers: dict[QuantifiedChain, Condition] = quantifiers or {}
        """A dictionary of quantified effects, with action- and UQV-bound atoms."""

        self._all_effects: dict[QuantifiedChain, Condition] = {
            **{QuantifiedChain.null(atom): effect for atom, effect in self.effects.items()},
            **self.quantifiers}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Action):
            return False
        return self.name == other.name and self.parameters == other.parameters and self.precondition == other.precondition \
            and self._all_effects == other._all_effects


    def apply(self, params: tuple[str, ...], state: dict[Atom, bool]) -> tuple[bool, dict[Atom, bool]]:
        mapping = {param: value for param, value in zip(self.parameters.keys(), params)}
        new_state = {**state}
        if not self.precondition.is_satisfied(mapping, state):
            return False, new_state
        pos_effects = []
        neg_effects = []
        for qchain, condition in self._all_effects.items():
            # effect sign
            if condition.outcome == Outcome.ADD_EFFECT:
                eff_list = pos_effects
            elif condition.outcome == Outcome.DEL_EFFECT:
                eff_list = neg_effects
            else:
                eff_list = []

            if qchain.is_null: # not quantified effect
                if condition.is_satisfied(mapping, state):
                    eff_list.append(qchain.ground_target(mapping))
            else:
                for qgrounding in qchain.ground_all(mapping, state):
                    if condition.is_satisfied(qgrounding, state):
                        eff_list.append(qchain.ground_target(qgrounding))
        for gatom in pos_effects:
            new_state[gatom] = True
        for gatom in neg_effects:
            new_state[gatom] = False
        return True, new_state


    def __str__(self):
        param_str = " ".join(f"{param} - {type.name}" for param, type in self.parameters.items())
        eff_str = "\n    ".join(chain.pprint(condition) for chain, condition in self._all_effects.items())
        return f"{self.name}({param_str})\n    precondition: {self.precondition}\n    effects: {eff_str}"

    def __repr__(self):
        return str(self)

class UPDomainConverter:

    def __init__(self, domain: Problem):
        self.domain = domain
        self.types = self.get_types_from_up()
        self.predicates = self.get_predicates_from_up()
        actions = [self.up_action_to_action(action) for action in self.domain.actions]
        self.actions = {action.name: action for action in actions}

    def get_types_from_up(self):
        types = {
            'object': Type('object', None),
        }
        for type in self.domain.user_types:
            type: UPType
            if type.name == 'object':
                continue
            if type.father is not None:
                father = types[type.father.name]
            else:
                father = None
            types[type.name] = Type(type.name, father)
        return types

    def get_predicates_from_up(self) -> dict[str, Atom]:
        predicates = {}
        for fluent in self.domain.fluents:
            fluent: UPFluent
            predicates[fluent.name] = Atom(
                fluent.name,
                tuple('?' + param.name.lstrip('?') for param in fluent.signature),
                tuple(self.types[param.type.name] for param in fluent.signature))
        return predicates

    def up_state_to_atoms(self, state: dict[FluentExpLike, bool]) -> dict[GroundedAtom, bool]:
        atoms = {}
        for fluent, value in state.items():
            atom_name = fluent.fluent().name
            atom_params = tuple('?' + param.name.lstrip('?') for param in fluent.fluent().signature)
            atom_objects = tuple(arg.object().name for arg in fluent.args)
            atom_types = tuple(self.types[arg.object().type.name] for arg in fluent.args)
            atoms[GroundedAtom(atom_name, atom_params, atom_types, atom_objects)] = value
        return atoms


    def up_objects_to_objects(self, objects: list[UPObject]) -> dict[str, Type]:
        return {obj.name: self.types[obj.type.name] for obj in objects}

    def up_fluent_to_atom(self, fluent: FNode) -> Atom:
        if fluent.node_type == OperatorKind.EQUALS:
            return None
        def param_name(arg: FNode | UPParameter) -> str:
            if isinstance(arg, UPParameter):
                return '?' + arg.name.lstrip('?')
            if arg.is_parameter_exp():
                return '?' + arg.parameter().name.lstrip('?')
            raise ValueError(f"Invalid argument: {arg}")
        fluent_sig = tuple(param_name(arg) for arg in fluent.fluent().signature)
        if len(fluent.args) > 0 and fluent.args[0].is_object_exp():
            params = fluent_sig # a grounded fluent is not action-bound
            types = tuple(self.types[arg.object().type.name] for arg in fluent.args)
        else:
            params = tuple(param_name(arg) for arg in fluent.args)
            types = tuple(self.types[arg.parameter().type.name] for arg in fluent.args)
        return Atom(fluent.fluent().name, params, types, fluent_sig)


    def up_action_to_action(self, up_action: UPAction) -> Action:
        action = Action(up_action.name, {'?' + param.name.lstrip('?'): self.types[param.type.name] for param in up_action.parameters})
        # Preconditions of the initial domain are assumed conjunctive
        pre_atoms: dict[Atom, bool] = {}
        for precondition in up_action.preconditions:
            precondition: FNode
            if precondition.is_fluent_exp():
                pre_atoms[self.up_fluent_to_atom(precondition)] = True
            elif precondition.is_not():
                pre_atoms[self.up_fluent_to_atom(precondition.args[0])] = False
            elif precondition.is_and():
                for child in precondition.args:
                    if child.is_fluent_exp():
                        pre_atoms[self.up_fluent_to_atom(child)] = True
                    elif child.is_not():
                        pre_atoms[self.up_fluent_to_atom(child.args[0])] = False
            elif precondition.is_or():
                disjunct = DisjunctiveAtom(tuple(self.up_fluent_to_atom(child) for child in precondition.args))
                pre_atoms[disjunct] = True
            else:
                raise ValueError(f"Invalid precondition: {precondition}")
        pre_atoms.pop(None, None)
        pre_atoms = {atom.bind({p: action.parameters[p] for p in atom.params}): v for atom, v in pre_atoms.items()}
        precondition_antecedent = Conjunction(pre_atoms)
        action.precondition = Condition(precondition_antecedent, Outcome.APPLICABLE)

        for effect in up_action.effects:
            effect_atom = self.up_fluent_to_atom(effect.fluent)
            if effect.condition.is_bool_constant():
                antecedent = effect.condition.bool_constant_value()
            elif effect.condition.is_and():
                terms = {}
                for child in effect.condition.args:
                    if child.is_fluent_exp():
                        terms[self.up_fluent_to_atom(child)] = True
                    elif child.is_not():
                        terms[self.up_fluent_to_atom(child.args[0])] = False
                antecedent = Conjunction(terms)
            elif effect.condition.is_fluent_exp():
                antecedent = Conjunction({self.up_fluent_to_atom(effect.condition): True})
            elif effect.condition.is_not():
                antecedent = Conjunction({self.up_fluent_to_atom(effect.condition.args[0]): False})
            else:
                raise ValueError(f"Invalid effect condition: {effect.condition}")
            if isinstance(antecedent, Conjunction) and effect_atom in antecedent:
                antecedent = {atom: value for atom, value in antecedent.items() if atom != effect_atom}
                if len(antecedent) == 0:
                    antecedent = True
            action.effects[effect_atom] = Condition(antecedent, Outcome.ADD_EFFECT if effect.value.bool_constant_value() else Outcome.DEL_EFFECT)
        return action


    def conjunction_to_up(self, conjunction: Conjunction, up_mapping: dict[str, UPParameter], domain: Problem) -> FNode:
        exps = []
        for atom, value in conjunction.items():
            params = [up_mapping[arg.replace('?', '')] for arg in atom.params]
            if value:
                exps.append(self.predicate_to_up(atom, params, domain))
            else:
                exps.append(Not(self.predicate_to_up(atom, params, domain)))
        return And(*exps)

    def predicate_to_up(self, predicate: Atom, up_params: Sequence[UPParameter], domain: Problem) -> FNode:
        up_predicate = domain.fluent(predicate.name)
        return FluentExp(up_predicate, up_params)

    def action_to_up(self, action: Action, domain: Problem) -> UPAction:
        up_action = UPAction(action.name,
                OrderedDict({param.replace('?', ''): domain.user_type(type.name) for param, type in action.parameters.items()}),
                _env=domain.environment)
        mapping = {param.name: param for param in up_action.parameters}
        if not isinstance(action.precondition.antecedent, bool):
            for conjunction in action.precondition.antecedent:
                conj = self.conjunction_to_up(conjunction, mapping, domain)
                up_action.add_precondition(conj)
        for qchain, condition in action._all_effects.items():
            qmapping = {**mapping}
            qvars = []
            for qvar, qtype in qchain.uqvs.items():
                qvars.append(UPVariable(qvar, domain.user_type(qtype.name)))
                qmapping[qvar.replace('?', '')] = qvars[-1]
            params = [qmapping[arg.replace('?', '')] for arg in qchain.target.params]
            effect = self.predicate_to_up(qchain.target, params, domain)
            value = condition.outcome == Outcome.ADD_EFFECT
            if isinstance(condition.antecedent, bool):
                if condition.antecedent:
                    antecedent = True
                else:
                    continue # else no effect
            else:
                if len(condition.antecedent) == 1:
                    conj = condition.antecedent[0]
                    antecedent = self.conjunction_to_up(conj, qmapping, domain)
                    if OHCAMConfig.instance().enforce_inequality:
                        for action_var in up_action.parameters:
                            for uqv_var in qmapping.values():
                                if uqv_var in set(up_action.parameters):
                                    continue
                                if action_var.type.is_subtype(uqv_var.type) or uqv_var.type.is_subtype(action_var.type):
                                    # add inequality constraint
                                    all_terms = (*(antecedent.args if not antecedent.is_fluent_exp() else [antecedent]), Not(Equals(action_var, uqv_var)))
                                    antecedent = And(*all_terms)
                else:
                    dnf = []
                    for conj in condition.antecedent:
                        conj = self.conjunction_to_up(conj, qmapping, domain)
                        if OHCAMConfig.instance().enforce_inequality:
                            for action_var in up_action.parameters:
                                for uqv_var in qmapping.values():
                                    if uqv_var in set(up_action.parameters):
                                        continue
                                    if action_var.type.is_subtype(uqv_var.type) or uqv_var.type.is_subtype(action_var.type):
                                        # add inequality constraint
                                        all_terms = (*(conj.args if not conj.is_fluent_exp() else [conj]), Not(Equals(action_var, uqv_var)))
                                        conj = And(*all_terms)
                        dnf.append(conj)
                    antecedent = Or(*dnf)

            up_action.add_effect(effect, value, antecedent, tuple(qvars))
        return up_action

    def up_transition_to_transition(self,
            up_state: dict[FluentExpLike, bool],
            up_action: ActionInstance,
            up_next_state: dict[FluentExpLike, bool],
            execution: str) -> tuple[dict[Atom, bool], tuple[str, ...], dict[Atom, bool], bool]:
        def up_state_dict_to_dict(up_state: dict[FluentExpLike, bool]) -> dict[GroundedAtom, bool]:
            grounded_atoms: dict[GroundedAtom, bool] = {}
            for fluent, value in up_state.items():
                atom = self.up_fluent_to_atom(fluent)
                objects = tuple(arg.object().name for arg in fluent.args)
                grounded_atom = GroundedAtom(atom.name, atom.params, atom.types, objects)
                grounded_atoms[grounded_atom] = value
            return grounded_atoms
        up_state = up_state_dict_to_dict(up_state)
        up_next_state = up_state_dict_to_dict(up_next_state)
        action_params = [arg.object().name for arg in up_action.actual_parameters]
        action = (up_action.action.name, *action_params)
        return up_state, action, up_next_state, execution != 'inapplicable'

    def new_up_domain(self, actions: list[Action]) -> Problem:
        new_domain = self.domain.clone()
        new_domain._env = get_environment()
        new_domain.clear_actions()
        for action in actions:
            new_action = self.action_to_up(action, new_domain)
            new_domain.add_action(new_action)
        return new_domain

def build_action_vocabulary(parameters: dict[str, Type], predicates: dict[str, Atom]) -> list[Atom]:
    """All lifted literals whose predicate argument types are compatible with action parameters."""
    param_names = list(parameters.keys())
    param_types = list(parameters.values())
    vocab = []
    for predicate in predicates.values():
        arg_types = predicate.types
        # For each predicate argument slot, collect action parameters whose type fits
        slot_candidates = []
        for slot_type in arg_types:
            candidates = [(param_names[i], pt) for i, pt in enumerate(param_types)
                          if slot_type.is_super_type(pt)]
            if not candidates:
                slot_candidates = None
                break
            slot_candidates.append(candidates)
        if slot_candidates is None:
            continue
        for binding in itertools.product(*slot_candidates):
            if len(set(binding)) != len(binding):
                continue
            vocab.append(predicate.bind({p: t for p, t in binding}))
    return sorted(vocab, key=str)
