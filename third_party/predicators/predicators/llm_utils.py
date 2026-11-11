from typing import Callable, Collection, List, Optional, Sequence, Set, Tuple
import logging

import PIL
from predicators.pretrained_model_interface import GoogleGeminiLLM, \
    GoogleGeminiVLM, LargeLanguageModel, OpenAILLM, OpenAIVLM, \
    VisionLanguageModel
from predicators.settings import CFG
from predicators.structs import GroundAtom, Object, ParameterizedOption, Predicate, State, Type, VLMPredicate, _Option
from predicators.utils import get_object_combinations, get_path_to_predicators_root

def create_vlm_predicate(
        name: str, types: Sequence[Type],
        get_vlm_query_str: Callable[[Sequence[Object]], str]) -> VLMPredicate:
    """Simple function that creates VLMPredicates with dummy classifiers, which
    is the most-common way these need to be created."""

    def _stripped_classifier(
            state: State,
            objects: Sequence[Object]) -> bool:  # pragma: no cover.
        raise Exception("VLM predicate classifier should never be called!")

    return VLMPredicate(name, types, _stripped_classifier, get_vlm_query_str)


def create_llm_by_name(
        model_name: str) -> LargeLanguageModel:  # pragma: no cover
    """Create particular llm using a provided name."""
    if "gemini" in model_name:
        return GoogleGeminiLLM(model_name)
    return OpenAILLM(model_name)


def create_vlm_by_name(
        model_name: str) -> VisionLanguageModel:  # pragma: no cover
    """Create particular vlm using a provided name."""
    if "gemini" in model_name:
        return GoogleGeminiVLM(model_name)
    return OpenAIVLM(model_name)

def parse_model_output_into_option_plan(
    model_prediction: str, objects: Collection[Object],
    types: Collection[Type], options: Collection[ParameterizedOption],
    parse_continuous_params: bool
) -> List[Tuple[ParameterizedOption, Sequence[Object], Sequence[float]]]:
    """Assuming text for an option plan that is predicted as text by a large
    model, parse it into a sequence of ParameterizedOptions coupled with a list
    of objects and continuous parameters that will be used to ground the
    ParameterizedOption.

    We assume the model's output is such that each line is formatted as
    option_name(obj0:type0, obj1:type1,...)[continuous_param0,
    continuous_param1, ...].
    """
    option_plan: List[Tuple[ParameterizedOption, Sequence[Object],
                            Sequence[float]]] = []
    # Setup dictionaries enabling us to easily map names to specific
    # Python objects during parsing.
    option_name_to_option = {op.name: op for op in options}
    type_name_to_type = {typ.name: typ for typ in types}
    obj_name_to_obj = {o.name: o for o in objects}
    options_str_list = model_prediction.split('\n')
    for option_str in options_str_list:
        option_str_stripped = option_str.strip()
        option_name = option_str_stripped.split('(')[0]
        # Skip empty option strs.
        if not option_str:
            continue
        if option_name not in option_name_to_option.keys() or \
            "(" not in option_str:
            logging.info(
                f"Line {option_str} output by model doesn't "
                "contain a valid option name. Terminating option plan "
                "parsing.")
            break
        if parse_continuous_params and "[" not in option_str:
            logging.info(
                f"Line {option_str} output by model doesn't contain a "
                "'[' and is thus improperly formatted.")
            break
        option = option_name_to_option[option_name]
        # Now that we have the option, we need to parse out the objects
        # along with specified types.
        try:
            start_index = option_str_stripped.index('(') + 1
            end_index = option_str_stripped.index(')', start_index)
        except ValueError:
            logging.info(
                f"Line {option_str} output by model is improperly formatted.")
            break
        typed_objects_str_list = option_str_stripped[
            start_index:end_index].split(',')
        objs_list = []
        continuous_params_list = []
        malformed = False
        for i, type_object_string in enumerate(typed_objects_str_list):
            object_type_str_list = type_object_string.strip().split(':')
            # We expect this list to be [object_name, type_name].
            if len(object_type_str_list) != 2:
                logging.info(f"Line {option_str} output by model has a "
                             "malformed object-type list.")
                malformed = True
                break
            object_name = object_type_str_list[0]
            type_name = object_type_str_list[1]
            if object_name not in obj_name_to_obj.keys():
                logging.info(f"Line {option_str} output by model has an "
                             "invalid object name.")
                malformed = True
                break
            obj = obj_name_to_obj[object_name]
            # Check that the type of this object agrees
            # with what's expected given the ParameterizedOption.
            if type_name not in type_name_to_type:
                logging.info(f"Line {option_str} output by model has an "
                             "invalid type name.")
                malformed = True
                break
            try:
                if option.types[i] not in type_name_to_type[
                        type_name].get_ancestors():
                    logging.info(
                        f"Line {option_str} output by model has an "
                        "invalid type that doesn't agree with the option"
                        f"{option}")
                    malformed = True
                    break
            except IndexError:
                # In this case, there's more supplied arguments than the
                # option has.
                logging.info(f"Line {option_str} output by model has an "
                             "too many object arguments for option"
                             f"{option}")
                malformed = True
                break
            objs_list.append(obj)
        # The types of the objects match, but we haven't yet checked if
        # all arguments of the option have an associated object.
        if len(objs_list) != len(option.types):
            malformed = True
        # Now, we attempt to parse out the continuous parameters.
        if parse_continuous_params:
            params_str_list = option_str_stripped.split('[')[1].strip(
                ']').split(',')
            for i, continuous_params_str in enumerate(params_str_list):
                stripped_continuous_param_str = continuous_params_str.strip()
                if len(stripped_continuous_param_str) == 0:
                    continue
                try:
                    curr_cont_param = float(stripped_continuous_param_str)
                except ValueError:
                    logging.info(f"Line {option_str} output by model has an "
                                 "invalid continouous parameter that can't be"
                                 "converted to a float.")
                    malformed = True
                    break
                continuous_params_list.append(curr_cont_param)
            if len(continuous_params_list) != option.params_space.shape[0]:
                logging.info(f"Line {option_str} output by model has "
                             "invalid continouous parameter(s) that don't "
                             f"agree with {option}{option.params_space}.")
                malformed = True
                break
        if not malformed:
            option_plan.append((option, objs_list, continuous_params_list))
    return option_plan


def get_prompt_for_vlm_state_labelling(
        prompt_type: str, atoms_list: List[str], label_history: List[str],
        imgs_history: List[List[PIL.Image.Image]],
        cropped_imgs_history: List[List[PIL.Image.Image]],
        skill_history: List[_Option]) -> Tuple[str, List[PIL.Image.Image]]:
    """Prompt for labelling atom values in a trajectory.

    Note that all our prompts are saved as separate txt files under the
    'vlm_input_data_prompts/atom_labelling' folder.
    """
    # Load the pre-specified prompt.
    filepath_prefix = get_path_to_predicators_root() + \
        "/predicators/datasets/vlm_input_data_prompts/atom_labelling/"
    try:
        with open(filepath_prefix + prompt_type + ".txt",
                  "r",
                  encoding="utf-8") as f:
            prompt = f.read()
    except FileNotFoundError:
        raise ValueError("Unknown VLM prompting option " + f"{prompt_type}")
    # The prompt ends with a section for 'Predicates', so list these.
    for atom_str in atoms_list:
        prompt += f"\n{atom_str}"

    if "img_option_diffs" in prompt_type:
        # In this case, we need to load the 'per_scene_naive' prompt as well
        # for the first timestep.
        with open(filepath_prefix + "per_scene_naive.txt",
                  "r",
                  encoding="utf-8") as f:
            init_prompt = f.read()
        for atom_str in atoms_list:
            init_prompt += f"\n{atom_str}"
        if len(label_history) == 0:
            return (init_prompt, imgs_history[0])
        # Now, we use actual difference-based prompting for the second timestep
        # and beyond.
        curr_prompt = prompt[:]
        curr_prompt_imgs = [imgs_history[-2][0], imgs_history[-1][0]]
        if CFG.vlm_include_cropped_images:
            if CFG.env in ["burger", "burger_no_move"]:  # pragma: no cover
                curr_prompt_imgs.extend(
                    [cropped_imgs_history[-1][1], cropped_imgs_history[-1][0]])
            else:
                raise NotImplementedError(
                    f"Cropped images not implemented for {CFG.env}.")
        curr_prompt += "\n\nSkill executed between states: "
        skill_name = skill_history[-1].name + str(skill_history[-1].objects)
        curr_prompt += skill_name
        if "label_history" in prompt_type:
            curr_prompt += "\n\nPredicate values in the first scene, " \
            "before the skill was executed: \n"
            curr_prompt += label_history[-1]
        return (curr_prompt, curr_prompt_imgs)
    # NOTE: we rip out only the first image from each trajectory
    # which is fine for most domains, but will be problematic for
    # situations in which there is more than one image per state.
    return (prompt, imgs_history[-1])


def query_vlm_for_atom_vals(
        vlm_atoms: Collection[GroundAtom],
        state: State,
        vlm: Optional[VisionLanguageModel] = None) -> Set[GroundAtom]:
    """Given a set of ground atoms, queries a VLM and gets the subset of these
    atoms that are true."""
    # Short-circuit this function in the case where there are no atoms that
    # need be labelled.
    if len(vlm_atoms) == 0:
        return set()
    true_atoms: Set[GroundAtom] = set()
    # Get quantities necessary to construct prompt to query VLM.
    assert state.simulator_state is not None
    assert isinstance(state.simulator_state["images"], list)
    curr_state_imgs = state.simulator_state["images"]
    vlm_atoms = sorted(vlm_atoms)
    atom_queries_list = [atom.get_vlm_query_str() for atom in vlm_atoms]
    prev_states_imgs_history = []
    prev_state_cropped_imgs_history: List[List[PIL.Image.Image]] = []
    if "state_history" in state.simulator_state:  # pragma: no cover
        prev_states = state.simulator_state["state_history"]
        prev_states_imgs_history = [
            s.simulator_state["images"] for s in prev_states
        ]
        if "cropped_images" in prev_states[0].simulator_state:
            prev_states_imgs_history = [
                s.simulator_state["cropped_images"] for s in prev_states
            ]
    images_history = prev_states_imgs_history + [curr_state_imgs]
    skill_history = []
    if "skill_history" in state.simulator_state:  # pragma: no cover
        skill_history = state.simulator_state["skill_history"]
    label_history = []
    if "vlm_label_history" in state.simulator_state:  # pragma: no cover
        label_history = state.simulator_state["vlm_label_history"]
    vlm_query_str, imgs = get_prompt_for_vlm_state_labelling(
        CFG.vlm_test_time_atom_label_prompt_type, atom_queries_list,
        label_history, images_history, prev_state_cropped_imgs_history,
        skill_history)
    # Query VLM.
    if vlm is None:
        vlm = create_vlm_by_name(CFG.vlm_model_name)  # pragma: no cover.
    vlm_input_imgs = \
        [PIL.Image.fromarray(img_arr) for img_arr in imgs] # type: ignore
    vlm_output = vlm.sample_completions(vlm_query_str,
                                        vlm_input_imgs,
                                        0.0,
                                        seed=CFG.seed,
                                        num_completions=1)
    assert len(vlm_output) == 1
    vlm_output_str = vlm_output[0]
    all_vlm_responses = vlm_output_str.strip().split("\n")
    # NOTE: this assumption is likely too brittle; if this is breaking, feel
    # free to remove/adjust this and change the below parsing loop accordingly!
    if len(atom_queries_list) != len(all_vlm_responses):
        return set()
    for i, (atom_query, curr_vlm_output_line) in enumerate(
            zip(atom_queries_list, all_vlm_responses)):
        try:
            assert atom_query + ":" in curr_vlm_output_line
            assert "." in curr_vlm_output_line
            value = curr_vlm_output_line.split(': ')[-1].strip('.').lower()
            if value == "true":
                true_atoms.add(vlm_atoms[i])
        except AssertionError:  # pragma: no cover
            continue
    return true_atoms


def abstract(state: State,
             preds: Collection[Predicate],
             vlm: Optional[VisionLanguageModel] = None) -> Set[GroundAtom]:
    """Get the atomic representation of the given state (i.e., a set of ground
    atoms), using the given set of predicates.

    Duplicate arguments in predicates are allowed.
    """
    # Start by pulling out all VLM predicates.
    vlm_preds = set(pred for pred in preds if isinstance(pred, VLMPredicate))
    # Next, classify all non-VLM predicates.
    atoms = set()
    for pred in preds:
        if pred not in vlm_preds:
            for choice in get_object_combinations(list(state), pred.types):
                if pred.holds(state, choice):
                    atoms.add(GroundAtom(pred, choice))
    if len(vlm_preds) > 0:
        # Now, aggregate all the VLM predicates and make a single call to a
        # VLM to get their values.
        vlm_atoms = set()
        for pred in vlm_preds:
            for choice in get_object_combinations(list(state), pred.types):
                vlm_atoms.add(GroundAtom(pred, choice))
        true_vlm_atoms = query_vlm_for_atom_vals(vlm_atoms, state, vlm)
        atoms |= true_vlm_atoms
    return atoms
