import subprocess
import os
import math
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import re
import mltl2ltlf as parser
import heapq
from collections import defaultdict

# PRISM executable and model paths (configurable via environment variables).
# To override the default PRISM executable location, set the PRISM_PATH environment variable.
prism_path = os.environ.get("PRISM_PATH", os.path.abspath("prism-mac/bin/prism"))
# Note: model_file is not currently used by the API and is retained only for illustrative purposes.
# Callers are expected to supply explicit model paths to the relevant functions.
model_file = os.environ.get("PRISM_MODEL_FILE", os.path.abspath("prism-mac/my_model.pm"))

def formula_parser(formula_str):
    # Regular-expression pattern for interval-bounded temporal operators G[·,·], F[·,·], and U[·,·].
    gfu_pattern_interval = r'\b(G|F|U)\[\s*(\d+)\s*,\s*(\d+)\s*\]'

    # Regular-expression pattern for upper-bounded operators F_<=·, G_<=·, and U_<=·.
    gfu_pattern_inequality_inclusive = r'\b(G|F|U)_<=\s*(\d+)'

    # Regular-expression pattern for strictly upper-bounded operators F_<·, G_<·, and U_<·.
    gfu_pattern_inequality_exclusive = r'\b(G|F|U)_<\s*(\d+)'

    param_counter = 1
    # Mapping from parameter identifiers to their corresponding (original) time bounds.
    param_map = {}
    vals_dict = {}

    # Rewriter for G[·,·], F[·,·], and U[·,·] into parameterized interval form.
    def gfu_replacer_interval(match):
        nonlocal param_counter
        op = match.group(1)
        a = match.group(2)
        b = match.group(3)

        t_a = f't_{param_counter}'
        t_b = f't_{param_counter + 1}'
        param_counter += 2

        vals_dict[t_a] = int(a)
        vals_dict[t_b] = int(b)
        param_map[t_b] = t_a

        return f'{op}_[{t_a},{t_b}]'

    def gfu_replacer_inequality_inclusive(match):
        nonlocal param_counter
        op = match.group(1)
        b = match.group(2)

        t_a = f't_{param_counter}'
        t_b = f't_{param_counter + 1}'
        param_counter += 2

        vals_dict[t_a] = 0
        vals_dict[t_b] = int(b)
        param_map[t_b] = t_a

        return f'{op}_[{t_a},{t_b}]'

    def gfu_replacer_inequality_exclusive(match):
        nonlocal param_counter
        op = match.group(1)
        b = match.group(2)

        t_a = f't_{param_counter}'
        t_b = f't_{param_counter + 1}'
        param_counter += 2

        vals_dict[t_a] = 0
        vals_dict[t_b] = int(b) - 1
        param_map[t_b] = t_a

        return f'{op}_[{t_a},{t_b}]'

    # Apply all syntactic rewritings to introduce explicit time parameters.
    formula_str = re.sub(gfu_pattern_interval, gfu_replacer_interval, formula_str)
    formula_str = re.sub(gfu_pattern_inequality_inclusive, gfu_replacer_inequality_inclusive, formula_str)
    formula_str = re.sub(gfu_pattern_inequality_exclusive, gfu_replacer_inequality_exclusive, formula_str)

    return formula_str, vals_dict, param_map

# Substitute concrete time bounds back into a parameterized formula.
def substitute_params(formula_str, param_values):
    pattern = re.compile(r'\b(t_\d+)\b')
    return pattern.sub(lambda m: str(param_values[m.group(1)]), formula_str)


def run_prism(input_formula, model_path):
    # Translate the input MLTL formula to an LTL formula and invoke PRISM for model checking.
    parser_input_formula = edit_parser_input(input_formula)
    parser_output_formula = parser.mltl2ltlf(parser_input_formula)
    final_formula = edit_parser_output(parser_output_formula)
    
    command = [
        prism_path,
        model_path,
        "-pf",
        "P>=1 " + "[" + final_formula + "]"
    ]
    # Execute PRISM and capture its output.
    output = subprocess.run(command, capture_output=True, text=True)
    if output.stderr:
        raise Exception("something failed!")
    match = re.search(r'Result:\s+(true|false)', output.stdout)
    if match:
        result = match.group(1)
        return(result == "true")
    else:
        print("PRISM output:\n", output.stdout)
        raise Exception("Could not parse PRISM result.")

    
# history is a mapping from atomic proposition names to their corresponding Boolean traces.
def model_builder(history, model_path, horizon):
    with open(model_path, "w") as f:
        f.write("dtmc\n")
        f.write(f"const int T = {str(horizon - 1)};\n")  
        f.write("module trace\n")
        f.write("\t" + "time : [0..T] init 0;\n")
        for atom in history:
            f.write("\t" +  f"{atom} : [0..1] init {str(history[atom][0])};\n")
        for i in range(1, horizon):
            base_str = "\t" + f"[] time={i-1} -> "
            for atom in history:
                base_str += f"({atom}'={str(history[atom][i])}) & "
            base_str += f"(time'={i});\n"
            f.write(base_str)
        f.write("\t" + f"[] time={horizon - 1} -> (time'={horizon - 1});\n")
        f.write("endmodule")

# Construct a PRISM property file from a list of (already instantiated) formulas.
# This helper assumes that candidate formulas and their distances have been computed upstream.
# The minimum-distance formula can then be tracked externally after each invocation.
def formula_builder(formula_list, formula_path):
    with open(formula_path, "w") as f:
        for formula in formula_list:
            parser_input_formula = edit_parser_input(formula)
            parser_output_formula = parser.mltl2ltlf(parser_input_formula)
            final_formula = edit_parser_output(parser_output_formula)
            f.write(f"P>=1 [ {final_formula} ];\n")
    

def edit_parser_output(formula_str):
    result = []
    for char in formula_str:
        if char.isalpha() and char != "X":
            result.append(f"({char}=1)")
        else:
            result.append(char)
    return "".join(result)

def edit_parser_input(formula_str):
    pattern = re.compile(r'\b(F|G|U)\b')
    return pattern.sub(r'\1_', formula_str)

def l1_distance(indices, pair_options, ref_pairs):
    dist = 0
    for i, idx in enumerate(indices):
        a, b = pair_options[i][idx]
        a_ref, b_ref = ref_pairs[i]
        dist += abs(a - a_ref) + abs(b - b_ref)
    return dist

def l1_ordered_batches(pair_options, ref_pairs):
    k = len(pair_options)
    heap = []
    seen = set()

    init_indices = tuple(0 for _ in range(k))
    init_dist = l1_distance(init_indices, pair_options, ref_pairs)
    heapq.heappush(heap, (init_dist, init_indices))
    seen.add(init_indices)

    current_dist = None
    current_batch = []

    while heap:
        dist, indices = heapq.heappop(heap)

        if current_dist is None:
            current_dist = dist

        if dist != current_dist:
            yield current_dist, current_batch
            current_dist = dist
            current_batch = []

        combination = [pair_options[i][idx] for i, idx in enumerate(indices)]
        current_batch.append(combination)

        for i in range(k):
            if indices[i] + 1 < len(pair_options[i]):
                new_indices = list(indices)
                new_indices[i] += 1
                new_indices = tuple(new_indices)
                if new_indices not in seen:
                    new_dist = l1_distance(new_indices, pair_options, ref_pairs)
                    heapq.heappush(heap, (new_dist, new_indices))
                    seen.add(new_indices)
                
    if current_batch:
        yield current_dist, current_batch

def entire_search_l1_batched(input_formula, model_path, horizon, max_workers=4, chunk_size=10):
    param_formula, vals_dict, param_map = formula_parser(input_formula)
    trial_vals = vals_dict.copy()

    pair_entities = [(base, dependent) for dependent, base in param_map.items()]
    k = len(pair_entities)

    pair_options = []
    ref_pairs = []

    for a, b in pair_entities:
        ref_a = vals_dict[a]
        ref_b = vals_dict[b]
        ref_pairs.append((ref_a, ref_b))
        valid_pairs = [(i, j) for i in range(horizon) for j in range(i + 1, horizon + 1)]
        sorted_pairs = sorted(valid_pairs, key=lambda pair: abs(pair[0] - ref_a) + abs(pair[1] - ref_b))
        pair_options.append(sorted_pairs)

    for dist, batch in l1_ordered_batches(pair_options, ref_pairs):
        # Partition the combinations at a fixed L1 distance into sub-batches and evaluate them in parallel worker threads.
        chunks = [batch[i:i+chunk_size] for i in range(0, len(batch), chunk_size)]

        def build_and_run_chunk(combinations_chunk):
            fd, tmp_path = tempfile.mkstemp(prefix=f"batch_formula_{dist}_", suffix=".pf", dir=os.path.abspath("prism-mac"))
            os.close(fd)
            try:
                local_trial_vals = trial_vals.copy()
                formula_lines_local = []
                for pair_combination in combinations_chunk:
                    for idx, (a, b) in enumerate(pair_entities):
                        local_trial_vals[a], local_trial_vals[b] = pair_combination[idx]
                    sub_formula = substitute_params(param_formula, local_trial_vals)
                    parser_input_formula = edit_parser_input(sub_formula)
                    parser_output_formula = parser.mltl2ltlf(parser_input_formula)
                    final_formula = edit_parser_output(parser_output_formula)
                    formula_lines_local.append(f"P>=1 [ {final_formula} ];")
                with open(tmp_path, "w") as f:
                    f.write("\n".join(formula_lines_local))
                results_local = run_prism_batch(model_path, tmp_path)
                return results_local
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        found_false = False
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(build_and_run_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                results = future.result()
                if any(r == "false" for r in results):
                    found_false = True
                    for f in futures:
                        f.cancel()
                    break
        if found_false:
            print("Found counterexample at L1 distance", dist)
            return dist

    print("Property is always true up to horizon =", horizon)
    return horizon


def run_prism_batch(model_path, formula_file_path):
    
    command = [prism_path, model_path, formula_file_path]
    output = subprocess.run(command, capture_output=True, text=True)
    if output.returncode != 0:
        raise Exception("PRISM exited with code {}.\nSTDERR:\n{}\nSTDOUT:\n{}".format(output.returncode, output.stderr, output.stdout))
    results = re.findall(r'Result:\s+(true|false)', output.stdout)
    return results

