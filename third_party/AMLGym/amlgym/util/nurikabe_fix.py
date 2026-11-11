"""Remove the `n0` constant from the nurikabe domain (and fix its problems/traces).

Original with constant
  (:types cell num group - object)
  (:constants n0 - num)
  (:action end-painting :parameters (?g - group) ... (remaining-cells ?g n0) ...)

Fixed (removed constant): `n0` becomes a regular object of a singleton subtype
`num0`, and `end-painting` takes it as an extra parameter, so grounding still
yields exactly one `end-painting` per group.

  (:types cell num group - object
     num0 - num)
  (:action end-painting :parameters (?g - group ?n0 - num0) ... (remaining-cells ?g ?n0) ...)

Problem files gain the object declaration:

  (:objects                          (:objects n0 - num0
    pos-0-0 ... - cell         -->     pos-0-0 ... - cell
    n1 n2 - num                        n1 n2 - num
    g0 g1 - group                      g0 g1 - group
  )                                  )

Trace files already declare `n0` (it is grounded into their object list), so it
is re-typed instead, and every `end-painting` gets the extra argument:

  (:objects n2 n0 n1 - num ...)      -->  (:objects n0 - num0 n2 n1 - num ...)
  (:action (end-painting g0))        -->  (:action (end-painting g0 n0))

The originals are never modified. By default this reads, for X=[0..4],
  amlgym/benchmarks/conditional/domains/nurikabe.pddl
  amlgym/benchmarks/conditional/problems/learning/trainX/nurikabe
  amlgym/benchmarks/conditional/problems/solving/nurikabe
  amlgym/benchmarks/conditional/traces/learning/trainX/nurikabe
  amlgym/benchmarks/conditional/traces/solving/trainX/nurikabe
and writes the fixed versions alongside them, as domains/nurikabe_fix.pddl and
.../nurikabe_fix directories. Output directories are recreated on every run, and
missing input directories are skipped.
"""

import argparse
import os
import re
import shutil
import sys

CONSTANT = "n0"
CONSTANT_TYPE = "num"
NEW_TYPE = "num0"
ACTION = "end-painting"
DOMAIN = "nurikabe"
FIX_DOMAIN = "nurikabe_fix"

BENCHMARK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmarks")
CONDITIONAL_DIR = os.path.join(BENCHMARK_DIR, "conditional")
TRAINS = range(5)

DEFAULT_DOMAIN = os.path.join(CONDITIONAL_DIR, "domains", "nurikabe.pddl")
DEFAULT_PROBLEM_DIRS = (
    [os.path.join(CONDITIONAL_DIR, "problems", "learning", f"train{i}", "nurikabe") for i in TRAINS]
    + [os.path.join(CONDITIONAL_DIR, "problems", "solving", "nurikabe")]
)
DEFAULT_TRACE_DIRS = (
    [os.path.join(CONDITIONAL_DIR, "traces", "learning", f"train{i}", "nurikabe") for i in TRAINS]
    + [os.path.join(CONDITIONAL_DIR, "traces", "solving", f"train{i}", "nurikabe") for i in TRAINS]
)

PROBLEM_EXT = ".pddl"
TRACE_EXT = ".trace"

# `n0` used as an object name, i.e. not already a variable (?n0) and not part of a longer name
NAME_RE = re.compile(rf"(?<![\w?-]){CONSTANT}(?![\w-])")


def _block(text: str, start: int) -> str:
    """Return the parenthesised block of `text` starting at the '(' at index `start`."""
    assert text[start] == "(", text[start:start + 20]
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError(f"unbalanced parentheses from offset {start}")


def _find_block(text: str, pattern: str) -> str:
    """Return the parenthesised block whose opening '(' is matched by `pattern`."""
    match = re.search(pattern, text)
    if match is None:
        return ""
    return _block(text, match.start())


def _object_groups(inner: str) -> list:
    """Split the body of an (:objects ...) / (:constants ...) block into (names, type) groups."""
    groups, names = [], []
    tokens = inner.split()
    i = 0
    while i < len(tokens):
        if tokens[i] == "-" and i + 1 < len(tokens):
            groups.append((names, tokens[i + 1]))
            names, i = [], i + 2
        else:
            names.append(tokens[i])
            i += 1
    if names:
        groups.append((names, None))
    return groups


def fix_domain(text: str) -> str:
    """Turn the `n0` constant into an object of the new `num0` subtype."""
    if re.search(rf"\(:types\b[^)]*\b{NEW_TYPE}\s+-\s+{CONSTANT_TYPE}\b", text):
        return text

    types = _find_block(text, r"\(:types\b")
    if not types:
        raise ValueError("no (:types ...) block found")
    text = text.replace(types, f"{types[:-1].rstrip()}\n{' ' * 16}{NEW_TYPE} - {CONSTANT_TYPE})", 1)

    constants = _find_block(text, r"\(:constants\b")
    if constants:
        remaining = [(names, kind) for names, kind in _object_groups(constants[len(":constants") + 1:-1])
                     if names != [CONSTANT]]
        if remaining:
            raise ValueError(f"unexpected constants besides {CONSTANT}: {constants}")
        # drop the whole block, and the line it sits on if nothing else is left there
        text = re.sub(rf"^[ \t]*{re.escape(constants)}[ \t]*\n", "", text, count=1, flags=re.MULTILINE)
        text = text.replace(constants, "", 1)

    action = _find_block(text, rf"\(:action\s+{ACTION}\b")
    if not action:
        raise ValueError(f"no (:action {ACTION} ...) found")
    fixed = NAME_RE.sub(f"?{CONSTANT}", action)  # (remaining-cells ?g n0) -> (remaining-cells ?g ?n0)
    params = _block(fixed, fixed.index("(", fixed.index(":parameters") + len(":parameters")))
    fixed = fixed.replace(params, f"{params[:-1].rstrip()} ?{CONSTANT} - {NEW_TYPE})", 1)
    return text.replace(action, fixed, 1)


def fix_objects(text: str) -> str:
    """Declare `n0` as a `num0` object at the front of the (:objects ...) block."""
    objects = _find_block(text, r"\(:objects\b")
    if not objects:
        raise ValueError("no (:objects ...) block found")

    inner = objects[len(":objects") + 1:-1]
    groups = _object_groups(inner)
    if any(CONSTANT in names and kind == NEW_TYPE for names, kind in groups):
        return text

    for names, kind in groups:
        if CONSTANT not in names:
            continue
        if len(names) == 1:  # the group would be left empty, so drop its type as well
            inner = re.sub(rf"{NAME_RE.pattern}\s*-\s*{kind}\b", "", inner, count=1)
        else:
            inner = NAME_RE.sub("", inner, count=1)
        break

    if "\n" not in inner:
        inner = " " + re.sub(r"[ \t]+", " ", inner).strip()
    fixed = f"(:objects {CONSTANT} - {NEW_TYPE}{inner})"
    return text.replace(objects, fixed, 1)


def fix_trace(text: str) -> str:
    """Fix the object list and pass `n0` to every end-painting action of a trace."""
    text = fix_objects(text)
    return re.sub(rf"\({ACTION}((?:\s+[\w-]+)*?)\s*\)",
                  lambda m: f"({ACTION}{m.group(1)} {CONSTANT})" if m.group(1).split()[-1:] != [CONSTANT] else m.group(0),
                  text)


def _fixed_path(path: str) -> str:
    """Map a `nurikabe` file or directory to its `nurikabe_fix` counterpart."""
    head, tail = os.path.split(path.rstrip(os.sep))
    if tail == DOMAIN:
        return os.path.join(head, FIX_DOMAIN)
    if tail == f"{DOMAIN}.pddl":
        return os.path.join(head, f"{FIX_DOMAIN}.pddl")
    raise ValueError(f"cannot derive output path for {path}: expected a '{DOMAIN}' directory or '{DOMAIN}.pddl'")


def _write_fixed(src: str, dst: str, fix, dry_run: bool) -> None:
    with open(src, "r") as f:
        fixed = fix(f.read())
    if not dry_run:
        with open(dst, "w") as f:
            f.write(fixed)


def _files(directory: str, extension: str) -> list:
    return sorted(f for f in os.listdir(directory) if extension in f)


def main(domain: str, problem_dirs: list, trace_dirs: list, dry_run: bool = False) -> None:
    if not os.path.isfile(domain):
        raise FileNotFoundError(domain)
    targets = [(domain, _fixed_path(domain), fix_domain)]

    for dirs, extension, fix in ((problem_dirs, PROBLEM_EXT, fix_objects), (trace_dirs, TRACE_EXT, fix_trace)):
        for d in dirs:
            if not os.path.isdir(d):
                print(f"skipping missing {d}")
                continue
            out_dir = _fixed_path(d)
            if not dry_run:
                if os.path.exists(out_dir):
                    shutil.rmtree(out_dir)
                os.makedirs(out_dir)
            targets += [(os.path.join(d, f), os.path.join(out_dir, f), fix) for f in _files(d, extension)]

    for src, dst, fix in targets:
        _write_fixed(src, dst, fix, dry_run)
        print(f"{'would write' if dry_run else 'wrote'} {dst}")
    print(f"{len(targets)} files {'to write' if dry_run else 'written'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="nurikabe domain file")
    parser.add_argument("--problems", nargs="*", default=DEFAULT_PROBLEM_DIRS, help="directories of problem files")
    parser.add_argument("--traces", nargs="*", default=DEFAULT_TRACE_DIRS, help="directories of trace files")
    parser.add_argument("--dry-run", action="store_true", help="report what would be written without writing")
    args = parser.parse_args()

    try:
        main(args.domain, args.problems, args.traces, args.dry_run)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"error: {e}")
