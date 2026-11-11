# Add current project to sys path
import os
import sys
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

from typing import List
import re
import logging
import shutil
import subprocess
import numpy as np

GEN_DIR = "pddl-generators"

def problem_satellite(seed: int = 123,
                      s: int = 1,
                      i: int = 1,
                      m: int = 1,
                      t: int = 1,
                      o: int = 1) -> str:
    """
    See `util/pddl-generators/satellite/README`.
    :param seed: random seed
    :param s: number of satellites
    :param i: maximum number of instruments
    :param m: number of modes
    :param t: number of targets
    :param o: number of observations
    :return: problem string
    """

    # Generate a problem
    result = subprocess.run(f"./{GEN_DIR}/satellite/satgen {seed} {s} {i} {m} {t} {o}".split(),
                            capture_output=True, text=True)
    problem = result.stdout

    return problem

def problem_briefcase(seed: int = 123,
                      o: int = 1) -> str:
    """
    See `util/pddl-generators/briefcaseworld/README`.
    :param seed: random seed
    :param o: number of objects
    :return: problem string
    """

    # Generate a problem
    result = subprocess.run(f"./{GEN_DIR}/briefcaseworld/briefcaseworld -o {o} -s {seed}".split(),
                            capture_output=True, text=True)
    problem = result.stdout

    return problem

def problem_citycar(seed: int = 123,
                    rows: int = 2,
                    columns: int = 2,
                    cars: int = 2,
                    garages: int = 2,
                    density: float = 1.0) -> str:
    """
    See `util/pddl-generators/citycar/README`.
    :param seed: random seed
    :param rows: number of rows
    :param columns: number of columns
    :param cars: number of cars
    :param garages: number of garages
    :param density: density of the road network
    :return: problem string
    """

    # Generate a problem
    result = subprocess.run(f"./{GEN_DIR}/citycar/generator.py {rows} {columns} {cars} {garages} --density {density} --seed {seed}".split(),
                            capture_output=True, text=True)
    problem = result.stdout
    problem = problem.replace("(= (total-cost) 0)", "")
    problem = problem.replace("(:metric minimize (total-cost))", "")

    return problem

def problem_maintenance(seed: int = 123,
                        days: int = 30,
                        planes: int = 30,
                        mechanics: int = 1,
                        cities: int = 3,
                        visits: int = 5) -> str:
    """
    See `util/pddl-generators/maintenance/README`.
    :param seed: random seed
    :param days: number of days
    :param planes: number of planes
    :param mechanics: number of mechanics
    :param cities: number of cities
    :param visits: number of visits
    :return: problem string
    """

    # Generate a problem
    result = subprocess.run(f"./{GEN_DIR}/maintenance/maintenance {days} {planes} {mechanics} {cities} {visits} --seed {seed}".split(),
                            capture_output=True, text=True)
    problem = result.stdout

    return problem

def problem_miconic_simpleadl(seed: int = 123,
                              floors: int = 3,
                              passengers: int = 2) -> str:
    """
    See `util/pddl-generators/miconic-simpleadl/README`.
    :param seed: random seed
    :param floors: number of floors
    :param passengers: number of passengers
    :return: problem string
    """

    # Generate a problem
    result = subprocess.run(f"./{GEN_DIR}/miconic-simpleadl/miconic -f {floors} -p {passengers} -r {seed}".split(),
                            capture_output=True, text=True)
    problem = result.stdout

    return problem

def problem_nurikabe(seed: int = 123,
                      width: int = 10,
                      height: int = 10) -> str:
    """
    See `util/pddl-generators/nurikabe/README`.
    :param seed: random seed
    :param width: width of the board
    :param height: height of the board
    :return: problem string
    """

    # Generate a problem
    result = subprocess.run(f"./{GEN_DIR}/nurikabe/generate.py random 1 {width} {height} {seed} pddl".split(),
                            capture_output=True, text=True)
    problem = result.stdout

    return problem
