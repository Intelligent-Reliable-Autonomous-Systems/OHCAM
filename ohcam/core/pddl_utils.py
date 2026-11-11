

from collections.abc import Iterator, Sequence
import itertools

from ohcam.core.pddl_repr import GroundedAtom, Type


def get_groundings(parameters: Sequence[Type], objects: dict[str, Type]) -> Iterator[tuple[str, ...]]:
    possible_mappings = []
    for type in parameters:
        arg_mappings = []
        for arg, arg_type in objects.items():
            if type.is_super_type(arg_type):
                arg_mappings.append(arg)
        possible_mappings.append(arg_mappings)
    for binding in itertools.product(*possible_mappings):
        if len(set(binding)) != len(binding):
            continue
        yield binding

def get_state_objects(state: dict[GroundedAtom, bool]) -> dict[str, Type]:
    objects: dict[str, Type] = {}
    for atom in state:
        for obj, type_ in zip(atom.objects, atom.types):
            if obj not in objects or not type_.is_super_type(objects[obj]):
                objects[obj] = type_
    return objects