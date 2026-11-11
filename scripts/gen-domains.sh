#!/bin/bash
# Regenerate the problems and traces of the benchmark domains.
cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/../third_party/AMLGym/amlgym/util"

echo "generating eval problems"
python gen_probs_conditional_solving.py
echo "generating train problems"
python gen_probs_conditional_learning.py 0
python gen_probs_conditional_learning.py 1
python gen_probs_conditional_learning.py 2
python gen_probs_conditional_learning.py 3
python gen_probs_conditional_learning.py 4

echo "gen eval traces"
python gen_trajs_solving_conditional.py
echo "gen train traces"
python gen_trajs_learning_conditional.py 0
python gen_trajs_learning_conditional.py 1
python gen_trajs_learning_conditional.py 2
python gen_trajs_learning_conditional.py 3
python gen_trajs_learning_conditional.py 4
