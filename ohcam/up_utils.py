"""Utility functions for Unified Planning."""

from collections import Counter, defaultdict
import hashlib
import itertools
import random
from typing import Iterator, Literal, Protocol, Sequence, Type

import numpy as np
from unified_planning.io import PDDLWriter
from unified_planning.model import (
    InstantaneousAction, OperatorKind, Problem, Type as UPType, Object as UPObject,
    Fluent as UPFluent, UPState, Parameter as UPParameter
)
from unified_planning.model.fnode import FNode
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import Bool as UPBool
from unified_planning.model.types import domain_size, domain_item

### Interfaces for UP FNode types
class ObjectExpLike(Protocol):
    """A UP Expression representing an object."""

    @property
    def node_type(self) -> Literal[OperatorKind.OBJECT_EXP]: ...

    @property
    def type(self) -> Literal[UPType]: ...

    def object(self) -> UPObject: ...

class FluentExpLike(Protocol):
    """A UP Expression representing a fluent."""
    @property
    def node_type(self) -> Literal[OperatorKind.FLUENT_EXP]: ...

    @property
    def args(self) -> list[ObjectExpLike]: ...

    @property
    def type(self) -> Literal[bool]: ...

    def fluent(self) -> UPFluent: ...

class NotFluentExpLike(Protocol):
    """A UP Expression representing a negated fluent."""
    @property
    def node_type(self) -> Literal[OperatorKind.NOT]: ...

    @property
    def type(self) -> Literal[bool]: ...

    @property
    def args(self) -> list[FluentExpLike]: ...

class ParameterExpLike(Protocol):
    """A UP Expression representing a parameter."""
    @property
    def node_type(self) -> Literal[OperatorKind.PARAM_EXP]: ...

    @property
    def type(self) -> Literal[UPType]: ...

    def parameter(self) -> UPParameter: ...

### State conversions
def up_state_to_dict(state: UPState | Sequence[FluentExpLike | NotFluentExpLike] | dict[FluentExpLike, bool], closed_world: bool = False) -> dict[FluentExpLike, bool]:
    """Convert a UP State to a dictionary of fluent expressions and their boolean assignments.

    Args:
        state: The UP State to convert
        closed_world: Enforce the closed world assumption. If True, any fluent that is not in the state is assumed to be false.
    Returns:
        A dictionary of fluent expressions and their boolean assignments.
    """
    if isinstance(state, UPState):
        state._condense_state()
        state_dict = {k: v.bool_constant_value() for k, v in state._values.items()}
    elif isinstance(state, dict):
        if isinstance(next(iter(state.values())), FNode):
            state_dict = {k: v.bool_constant_value() for k, v in state.items()}
        else:
            state_dict = state
    else:
        dict_state = {}
        for fexp in state:
            if fexp.node_type == OperatorKind.NOT:
                dict_state[fexp.args[0]] = False
            else:
                dict_state[fexp] = True
        state_dict = dict_state
    if closed_world:
        all_fluents = enumerate_groundings_from_state(state_dict)
        for fluent in all_fluents:
            if fluent not in state_dict:
                state_dict[fluent] = False
    return state_dict

def dict_state_to_up_state(state: dict[FluentExpLike, bool], problem: Problem) -> UPState:
    """Convert a dictionary of fluent expressions and their boolean assignments to a UP State."""
    return UPState({k: UPBool(v) for k, v in state.items()}, problem)

def all_objects_from_state(state: dict[FluentExpLike, bool]) -> list[UPObject]:
    """Get all objects referenced in a dictionary of fluent expressions and their boolean assignments."""
    return list(set([oexp.object() for fexp in state.keys() for oexp in fexp.args]))


def enumerate_groundings_from_state(state: dict[FluentExpLike, bool]) -> Iterator[FluentExpLike]:
    """Enumerate all grounded fluent expressions using fluents and objects from the state.

    Args:
        state: A dictionary of fluent expressions and their boolean assignments.
    Returns:
        An iterator over all grounded fluent expressions.
    """
    all_fluents = set(state.keys())
    all_objects = set(all_objects_from_state(state))
    for grounded_fluent_exp in all_fluents:
        fluent = grounded_fluent_exp.fluent()
        if len(fluent.signature) == 0:
            yield fluent()
            continue
        compatible_objects = []
        for param in fluent.signature:
            param: UPParameter
            compatible_objects.append([obj for obj in all_objects if param.type.is_compatible(obj.type)])
        for objects in itertools.product(*compatible_objects):
            yield fluent(*objects)


def get_fluent_possible_parameters(problem: Problem, fluent: UPFluent) -> Iterator[tuple[ParameterExpLike, ...]]:
    """Get all possible parameter groundings for a fluent.

    Args:
        problem: The problem to get all possible parameter groundings from
        fluent: The fluent to get all possible parameter groundings for
    Returns:
        An iterator over all possible parameter groundings.
    """
    # if the action does not have parameters, it has only one possible parameter: the empty tuple
    if len(fluent.signature) == 0:
        return iter([tuple()])

    type_list: list[Type] = [param.type for param in fluent.signature]

    # e.g. in-loc(Robot, Location) with robots r1, r2 and locations l1, l2 yields the product
    # (r1, l1), (r1, l2), (r2, l1), (r2, l2)
    domain_sizes = [domain_size(problem, t) for t in type_list]
    items_list: list[list[FNode]] = []
    for size, type in zip(domain_sizes, type_list):
        items_list.append(
            [domain_item(problem, type, j) for j in range(size)]
        )

    return itertools.product(*items_list)

### Action utilities



def sample_action_from_state(
        problem: Problem,
        state: UPState | dict[FluentExpLike, bool],
        action_name: str | None = None,
        applicable_only: bool = True,
        relax_terms: int = 0,
        sample_on_failure: bool = False) -> ActionInstance | None:
    """Sample an action based on the state and present objects

    Can sample either an applicable action or a random action grounding.
    Can relax some precondition terms to allow inapplicable actions that are closer to the preconditions.

    Args:
        problem: The problem to sample an action from
        state: The state to sample an action in
        action_name: Optionally, the name of the action to sample
        applicable_only: Whether to only sample applicable actions. If False, will sample a random grounding.
        relax_terms: The number of terms to relax in the preconditions. Only used if applicable_only is True.
        sample_on_failure: Whether to fall back to a random grounding if no grounding satisfies the preconditions.
    Returns:
        An action instance, or None if no grounding was found
    """
    if isinstance(state, UPState):
        state = up_state_to_dict(state)
    max_tries = 50
    for _ in range(max_tries):
        if action_name is None:
            up_action: InstantaneousAction = random.choice(problem.actions)
        else:
            up_action = problem.action(action_name)
        if not applicable_only:
            # sample a random grounding
            partial = {}
            break
        pre_fluents = []
        for precondition in up_action.preconditions:
            precondition: FNode
            if precondition.is_fluent_exp():
                pre_fluents.append((precondition, True))
            elif precondition.is_not():
                pre_fluents.append((precondition.args[0], False))
            elif precondition.is_and():
                for child in precondition.args:
                    if child.is_fluent_exp():
                        pre_fluents.append((child, True))
                    elif child.is_not():
                        pre_fluents.append((child.args[0], False))
                    elif child.is_or():
                        children = []
                        for or_child in child.args:
                            if or_child.is_fluent_exp():
                                children.append((or_child, True))
                            elif or_child.is_not():
                                children.append((or_child.args[0], False))
                        pre_fluents.append((('or', *children), True))
            elif precondition.is_or():
                children = []
                for child in precondition.args:
                    if child.is_fluent_exp():
                        children.append((child, True))
                    elif child.is_not():
                        children.append((child.args[0], False))
                pre_fluents.append((('or', *children), True))

        for _ in range(relax_terms):
            # randomly remove a precondition
            if len(pre_fluents) > 0:
                pre_fluents.pop(np.random.randint(len(pre_fluents)))
        partial = next(_unify_pattern(pre_fluents, state, problem, up_action), None)
        if partial is not None:
            break
        else:
            if sample_on_failure:
                partial = {}
            else:
                partial = None

    if partial is None:
        return None
    # fill in any unbound parameters randomly
    return _uniform_action_grounding(problem, up_action, partial)

def _unify_pattern(pattern: list[FluentExpLike, bool], state: dict[FluentExpLike, bool], problem: Problem, action: InstantaneousAction) -> Iterator[dict[UPParameter, UPObject]]:
    """Find all valid groundings of pattern against state.
    pattern: Conjunction of (Literal, bool) — literal and required truth value
    state: dict[Atom, bool]
    Yields: dict[UPParameter, UPObject] — variable-to-object bindings
    """
    # Index state for fast lookup
    by_predicate = defaultdict(list[FluentExpLike])
    for atom, val in state.items():
        if val:
            by_predicate[atom.fluent().name].append((atom.args))

    # Find candidate atoms for each pattern literal
    candidate_lists: list[tuple[tuple[ParameterExpLike, ...], list[ObjectExpLike]]] = []
    for literal, value in pattern:
        if isinstance(literal, tuple) and literal[0] == 'or':
            dict_candidates = []
            args = []
            for child, cvalue in literal[1:]:
                child_candidates = by_predicate.get(child.fluent().name, [])
                if not cvalue:
                    child_candidates = list(set(get_fluent_possible_parameters(problem, child.fluent())) - set(child_candidates))
                for candidate in child_candidates:
                    dict_candidates.append({param: obj for param, obj in zip(child.args, candidate)})
                for arg in child.args:
                    if arg not in args:
                        args.append(arg)
            candidates = [tuple(dc.get(arg, None) for arg in args) for dc in dict_candidates]
        else:
            args = literal.args
            if not literal.is_fluent_exp():
                continue
            candidates = by_predicate.get(literal.fluent().name, [])
            if not value:
                all_bindings = get_fluent_possible_parameters(problem, literal.fluent())
                candidates = list(set(all_bindings) - set(candidates))
        candidates = [c for c in candidates if
                all([action.parameter(param.parameter().name).type in set(obj.object().type.ancestors) for param, obj in zip(literal.args, c)])]
        if not candidates:
            return None # No way to satisfy this literal
        np.random.shuffle(candidates)
        candidate_lists.append((args, candidates))
    # satisfy (not) predicates first
    # least constrained variables first heuristic
    candidate_lists.sort(key=lambda x: len(x[1]))
    # Backtracking search
    def search(idx, bindings):
        if idx == len(candidate_lists):
            yield {param.parameter() if param.is_parameter_exp() else param.object():
                    obj.object() for param, obj in bindings.items()}
            return
        var_args, candidates = candidate_lists[idx]
        for atom_args in candidates:
            new_bindings = dict(bindings)
            ok = True
            for var, obj in zip(var_args, atom_args):
                if obj is None:
                    continue
                if var in new_bindings:
                    if new_bindings[var] != obj:
                        ok = False
                        break
                else:
                    new_bindings[var] = obj
            if ok:
                yield from search(idx + 1, new_bindings)

    yield from search(0, {})

def _uniform_action_grounding(problem: Problem, action: InstantaneousAction, partial: dict[UPParameter, UPObject]) -> ActionInstance:
    grounding = dict(partial)
    for param in action.parameters:
        if param not in grounding:
            param: UPParameter
            # avoid grounding the same object to multiple parameters -- identifiability assumption
            compatible = [obj for obj in problem.all_objects if obj not in grounding.values() and param.type.is_compatible(obj.type)]
            if not compatible:
                return None
            grounding[param] = np.random.choice(compatible)
    return ActionInstance(action, [grounding.get(param, None) for param in action.parameters])

### Problem utilities
def initialize_problem_from_state(domain: Problem, state: dict[FluentExpLike, bool], objects: list[UPObject] | None = None) -> Problem:
    """Define a problem from an initial state."""
    state = up_state_to_dict(state)
    if objects is None:
        objects = all_objects_from_state(state)
    new_problem = domain.clone()
    new_problem._objects = []
    new_objects = {}
    for obj in objects:
        obj: UPObject
        new_obj = UPObject(obj.name, new_problem.user_type(obj.type.name), environment=new_problem.environment)
        if not new_problem._has_name_method(new_obj.name):
            new_problem.add_object(new_obj)
            new_objects[obj.name] = new_obj
        else:
            new_objects[obj.name] = next(obj for obj in new_problem.all_objects if obj.name == obj.name)
    new_problem._initial_value = {}
    for fexp, val in state.items():
        fexp: FluentExpLike
        new_fexp = new_problem.fluent(fexp.fluent().name)(*[new_objects[arg.object().name] for arg in fexp.args])
        new_problem.set_initial_value(new_fexp, val)
    return new_problem

def copy_problem_into_domain(problem: Problem, domain: Problem):
    """Combine the initial state and goal of a problem into a domain with actions."""
    new_problem = domain.clone()
    new_objects = {}
    for obj in problem.all_objects:
        obj: UPObject
        new_obj = UPObject(obj.name, new_problem.user_type(obj.type.name), environment=new_problem.environment)
        if not new_problem._has_name_method(new_obj.name):
            new_problem.add_object(new_obj)
            new_objects[obj.name] = new_obj
        else:
            new_objects[obj.name] = next(obj for obj in new_problem.all_objects if obj.name == obj.name)
    for fexp, val in up_state_to_dict(problem.initial_values).items():
        fexp: FluentExpLike
        new_fexp = new_problem.fluent(fexp.fluent().name)(*[new_objects[arg.object().name] for arg in fexp.args])
        new_problem.set_initial_value(new_fexp, val)
    for goal in problem.goals:
        goal: FNode
        new_problem.add_goal(goal)
    return new_problem

def reorder_problem_actions(problem: Problem, target: Problem):
    """Reorder the actions of a problem to match the actions of a target problem."""
    new_actions = []
    for target_action in target.actions:
        for action in problem.actions:
            root = action.name.split('__')[0]
            if root == target_action.name:
                new_actions.append(action)
    for action in problem.actions:
        if action not in new_actions:
            new_actions.append(action)
    problem._actions = new_actions

def flatten_preconditions(problem: Problem):
    for action in problem.actions:
        all_preconditions = []
        for precondition in action.preconditions:
            if precondition.is_and():
                all_preconditions.extend(precondition.args)
            else:
                all_preconditions.append(precondition)
        action._preconditions = all_preconditions

def sort_preconditions(problem: Problem):
    flatten_preconditions(problem)
    for action in problem.actions:
        all_preconditions = []
        for precondition in action.preconditions:
            all_preconditions.append(precondition)
        action._preconditions = sorted(all_preconditions, key=lambda x: str(x.args[0]) if x.is_not() else str(x))

def sort_effects(problem: Problem):
    for action in problem.actions:
        all_effects = []
        for effect in action.effects:
            all_effects.append(effect)
        action._effects = sorted(action.effects, key=lambda x: str(x))

def empty_domain(domain: Problem) -> Problem:
    new_domain = domain.clone()
    for action in new_domain.actions:
        action: InstantaneousAction
        action.clear_preconditions()
        action.clear_effects()
    return new_domain

### Functional hashing

# Operators whose arguments can be reordered. AND/OR are also flattened and deduplicated.
_COMMUTATIVE_OPERATORS = frozenset([OperatorKind.AND, OperatorKind.OR, OperatorKind.IFF, OperatorKind.EQUALS])
# Operators rendered as `(op args...)` with no further normalization
_PLAIN_OPERATORS = frozenset([
    OperatorKind.NOT, OperatorKind.IMPLIES, OperatorKind.IFF, OperatorKind.EQUALS, OperatorKind.LE,
    OperatorKind.LT, OperatorKind.PLUS, OperatorKind.MINUS, OperatorKind.TIMES, OperatorKind.DIV,
])
# Beyond this many ways of naming same-typed variables of one quantifier, keep their declared order
_MAX_BINDER_PERMUTATIONS = 720

def functional_hash(problem: Problem) -> str:
    """Hash a problem by what it means rather than how it is written.

    Problems that differ only in the order of declarations, actions, preconditions, effects or the
    arguments of and/or/=, in action parameter names, or in quantified variable names hash equal.
    See ``canonical_form``. Raises NotImplementedError for features it doesn't normalize (durative
    actions, processes, metrics, ...), so callers can fall back to hashing the text.
    """
    return hashlib.sha256(canonical_form(problem).encode()).hexdigest()

def canonical_form(problem: Problem) -> str:
    """A text form of a problem that is equal for problems that are equal up to reordering and renaming.

    - Declarations (types, fluents, objects, actions, initial values) are sorted by name.
    - Action parameters are named by position (`$0`, `$1`, ...), since plans bind them positionally.
    - Quantified variables are named per type by nesting depth (`$can.0`, then `$can.1` inside it).
      Same-typed variables of one quantifier take whichever naming gives the smallest text.
    - and/or are flattened, deduplicated and sorted; a single conjunct stands alone and an empty one is `true`.
      A forall over a conjunction is split into one forall per conjunct.
    - Each effect is one clause `(forall (vars) (kind fluent value condition))` on a single fluent,
      matching how UP parses `(forall (?x) (when c (and e1 e2)))` into two effects. Effects are deduplicated.

    Names of the problem, types, fluents, objects and actions are kept, since other files refer to them.
    """
    _check_canonicalizable(problem)
    lines = [_sexp("problem", problem.name)]
    for user_type in sorted(problem.user_types, key=lambda t: t.name):
        lines.append(_sexp("type", user_type.name, user_type.father.name if user_type.father else "-"))
    defaults = problem.fluents_defaults
    for fluent in sorted(problem.fluents, key=lambda f: f.name):
        default = _canonical_expression(defaults[fluent], {}, Counter()) if fluent in defaults else "-"
        lines.append(_sexp("fluent", fluent.name, _type_name(fluent.type),
                           _sexp(*(_type_name(p.type) for p in fluent.signature)), default))
    for obj in sorted(problem.all_objects, key=lambda o: o.name):
        lines.append(_sexp("object", obj.name, _type_name(obj.type)))
    for action in sorted(problem.actions, key=lambda a: a.name):
        names = {param: f"${i}" for i, param in enumerate(action.parameters)}
        effects = sorted({_canonical_effect(effect, names) for effect in action.effects})
        lines.append(_sexp(
            "action", action.name,
            _sexp(*(_type_name(param.type) for param in action.parameters)),
            _canonical_conjunction(action.preconditions, names, Counter()),
            _sexp(*effects),
        ))
    initial_values = sorted(_sexp(_canonical_expression(fluent, {}, Counter()), _canonical_expression(value, {}, Counter()))
                            for fluent, value in problem.explicit_initial_values.items())
    lines.append(_sexp("init", *initial_values))
    lines.append(_sexp("goal", _canonical_conjunction(problem.goals, {}, Counter())))
    return "\n".join(lines)

def _check_canonicalizable(problem: Problem):
    for action in problem.actions:
        if type(action) is not InstantaneousAction:
            raise NotImplementedError(f"canonical_form doesn't support {type(action).__name__} {action.name}")
        if action.simulated_effect is not None:
            raise NotImplementedError(f"canonical_form doesn't support the simulated effect of {action.name}")
    unsupported = {
        "quality metrics": problem.quality_metrics,
        "timed goals": problem.timed_goals,
        "timed effects": problem.timed_effects,
        "trajectory constraints": problem.trajectory_constraints,
        "state invariants": problem.state_invariants,
        "processes and events": problem.natural_transitions,
    }
    for feature, values in unsupported.items():
        if values:
            raise NotImplementedError(f"canonical_form doesn't support {feature}")

def _sexp(*parts: str) -> str:
    return f"({' '.join(parts)})"

def _type_name(up_type: UPType) -> str:
    return up_type.name if up_type.is_user_type() else str(up_type)

def _conjuncts(node: FNode) -> Iterator[FNode]:
    """The conjuncts of a formula, flattening nested ands and splitting foralls over conjunctions."""
    if node.is_and():
        for arg in node.args:
            yield from _conjuncts(arg)
    elif node.is_forall():
        body_conjuncts = list(_conjuncts(node.arg(0)))
        if len(body_conjuncts) == 1:
            yield node
        else:
            expression_manager = node.environment.expression_manager
            for conjunct in body_conjuncts:
                yield expression_manager.Forall(conjunct, *node.variables())
    else:
        yield node

def _disjuncts(node: FNode) -> Iterator[FNode]:
    if node.is_or():
        for arg in node.args:
            yield from _disjuncts(arg)
    else:
        yield node

def _canonical_conjunction(nodes: Sequence[FNode], names: dict, depths: Counter) -> str:
    conjuncts = sorted({_canonical_expression(c, names, depths) for node in nodes for c in _conjuncts(node)})
    if len(conjuncts) == 1:
        return conjuncts[0]
    return _sexp("and", *conjuncts) if conjuncts else "true"

def _canonical_expression(node: FNode, names: dict, depths: Counter) -> str:
    """Render an expression with parameters and variables renamed by ``names``.

    ``depths`` counts the quantified variables of each type in scope, which numbers the next ones.
    """
    if node.is_fluent_exp():
        return _sexp(node.fluent().name, *(_canonical_expression(arg, names, depths) for arg in node.args))
    if node.is_parameter_exp():
        return names[node.parameter()]
    if node.is_variable_exp():
        return names[node.variable()]
    if node.is_object_exp():
        return node.object().name
    if node.is_constant():
        return str(node.constant_value()).lower()
    if node.is_and():
        return _canonical_conjunction([node], names, depths)
    if node.is_forall():
        conjuncts = list(_conjuncts(node))
        if len(conjuncts) > 1:
            return _canonical_conjunction(conjuncts, names, depths)
        return _canonical_binder("forall", node.variables(),
                                 lambda names, depths: _canonical_expression(node.arg(0), names, depths), names, depths)
    if node.is_exists():
        return _canonical_binder("exists", node.variables(),
                                 lambda names, depths: _canonical_expression(node.arg(0), names, depths), names, depths)
    if node.is_or():
        disjuncts = sorted({_canonical_expression(d, names, depths) for d in _disjuncts(node)})
        if len(disjuncts) == 1:
            return disjuncts[0]
        return _sexp("or", *disjuncts) if disjuncts else "false"
    if node.node_type in _PLAIN_OPERATORS:
        args = [_canonical_expression(arg, names, depths) for arg in node.args]
        if node.node_type in _COMMUTATIVE_OPERATORS:
            args.sort()
        return _sexp(node.node_type.name.lower(), *args)
    raise NotImplementedError(f"canonical_form doesn't support {node.node_type.name} expressions: {node}")

def _canonical_binder(head: str, variables: Sequence, render_body, names: dict, depths: Counter) -> str:
    """Render a quantifier, naming its variables per type by nesting depth.

    The variables of a quantifier are unordered, so same-typed ones could take their names in any
    order; take the order that renders the smallest body, so the result doesn't depend on it.
    """
    by_type: dict[str, list] = defaultdict(list)
    for variable in variables:
        by_type[_type_name(variable.type)].append(variable)
    type_names = sorted(by_type)
    inner_depths = depths.copy()
    for type_name in type_names:
        inner_depths[type_name] += len(by_type[type_name])
    binder = _sexp(*(f"${type_name}.{depths[type_name] + i} - {type_name}"
                     for type_name in type_names for i in range(len(by_type[type_name]))))

    orderings_per_type = [list(itertools.permutations(by_type[type_name])) for type_name in type_names]
    if np.prod([len(orderings) for orderings in orderings_per_type]) > _MAX_BINDER_PERMUTATIONS:
        orderings_per_type = [[tuple(by_type[type_name])] for type_name in type_names]
    bodies = []
    for orderings in itertools.product(*orderings_per_type):
        inner_names = dict(names)
        for type_name, ordering in zip(type_names, orderings):
            for i, variable in enumerate(ordering):
                inner_names[variable] = f"${type_name}.{depths[type_name] + i}"
        bodies.append(render_body(inner_names, inner_depths))
    return _sexp(head, binder, min(bodies))

def _canonical_effect(effect, names: dict) -> str:
    def render_body(names: dict, depths: Counter) -> str:
        return _sexp(effect.kind.name.lower(), _canonical_expression(effect.fluent, names, depths),
                     _canonical_expression(effect.value, names, depths),
                     _canonical_expression(effect.condition, names, depths))
    if effect.is_forall():
        return _canonical_binder("forall", effect.forall, render_body, names, Counter())
    return render_body(names, Counter())

def get_pddl_writer(domain: Problem) -> PDDLWriter:
    try:
        from unified_planning.io.pddl_writer import PDDLWriterFormat
        writer_format = PDDLWriterFormat(
            indentation=4,
            expression_style='expanded',
            allow_fixed_spacing=False,
            use_exact_param_names=True,
            empty_action_and=True
        )
        writer = PDDLWriter(domain, format=writer_format, empty_preconditions=True)
    except ImportError:
        writer = PDDLWriter(domain, empty_preconditions=True)
    # UP infers hierarchical typing from the types actions use, so a domain whose only subtype-using action was
    # dropped (e.g. nurikabe's end-painting, ?n0 - num0) would be written with flat types and lose `num0 - num`
    if any(t.father is not None for t in domain.user_types):
        writer.problem_kind.set_typing("HIERARCHICAL_TYPING")
    return writer
