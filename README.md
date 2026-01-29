# TempEST: Temporal Exploration for Stress Testing

This repository contains the implementation of TempEST, a tool for probabilistic model checking of Metric Temporal Logic (MTL) formulas using the PRISM model checker.

## Overview

TempEST provides functionality for:
- Building Discrete-Time Markov Chain (DTMC) models from execution traces
- Parsing and converting Metric Temporal Logic (MTL) formulas to Linear Temporal Logic (LTL) formulas
- Performing L1-distance-based search for counterexamples
- Parallel batch processing of PRISM model checking queries

## Requirements

### Python Dependencies

Install Python dependencies using:

```bash
pip install -r requirements.txt
```

### PRISM Model Checker

TempEST requires PRISM to be installed and accessible. PRISM can be downloaded from:
- **Official Website**: https://www.prismmodelchecker.org/
- **GitHub**: https://github.com/prismmodelchecker/prism

#### Installation Instructions

1. Download PRISM from the official website or clone from GitHub
2. Extract/compile PRISM according to the official instructions
3. Configure the PRISM path using one of the following methods:

   **Option A: Environment Variable (Recommended)**
   ```bash
   export PRISM_PATH="/path/to/prism/bin/prism"
   ```

   **Option B: Modify `tempest.py`**
   Update the `prism_path` variable in `tempest.py`:
   ```python
   prism_path = os.environ.get("PRISM_PATH", os.path.abspath("path/to/prism/bin/prism"))
   ```

   **Default**: If neither is set, TempEST assumes PRISM is in `prism-mac/bin/prism` relative to the script (macOS default).

## File Structure

```
.
├── tempest.py          # Main implementation file
├── mltl2ltlf.py        # MTL to LTL formula converter
├── mltl.lark           # Lark grammar file for parsing MTL formulas
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

**Important**: The `mltl.lark` file must be in the same directory as `mltl2ltlf.py` for the parser to work correctly.

## Dependencies and Attribution

### MLTL2LTLf Converter

The `mltl2ltlf.py` module is based on the [mltl2ltlf](https://github.com/lu-w/mltl2ltlf) library by lu-w, with adaptations for use in TempEST.

**Original Repository**: https://github.com/lu-w/mltl2ltlf  
**License**: MIT License

The original library converts Mission-Time Linear Temporal Logic (MLTL) to Linear Temporal Logic on Finite Traces (LTLf). TempEST includes an adapted version of this converter to handle MTL formula parsing and conversion.

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install PRISM** (see Requirements section above)

3. **Configure PRISM path** (choose one):
   - Set environment variable: `export PRISM_PATH="/path/to/prism/bin/prism"`
   - Or modify `prism_path` in `tempest.py` (see Requirements section)

4. **Run the example**:
   ```bash
   python tempest.py
   ```

## Usage

### Basic Example

```python
import tempest

# Build a DTMC model from a trace
history = {"a": [0, 0, 1, 0, 1], "b": [0, 1, 0, 1, 0]}
model_path = "model.pm"
horizon = 5
tempest.model_builder(history, model_path, horizon)

# Check an MTL formula
formula = "F[1, 2] a"
result = tempest.run_prism(formula, model_path)
print(f"Formula satisfied: {result}")
```

### L1-Distance Search

To find the minimum L1 distance to a counterexample:

```python
formula = "F[5, 30] p"
model_path = "model.pm"
horizon = 30
min_distance = tempest.entire_search_l1_batched(
    formula, 
    model_path, 
    horizon,
    max_workers=4,      # Number of parallel workers
    chunk_size=10        # Formulas per batch
)
print(f"Minimum L1 distance: {min_distance}")
```

## Key Functions

### `model_builder(history, model_path, horizon)`
Builds a PRISM DTMC model from a trace history.

**Parameters:**
- `history`: Dictionary mapping atom names to lists of boolean values (trace)
- `model_path`: Path where the PRISM model file will be written
- `horizon`: Maximum time horizon for the model

### `run_prism(input_formula, model_path)`
Checks if an MTL formula is satisfied by the PRISM model.

**Parameters:**
- `input_formula`: MTL formula string (e.g., `"F[1, 2] a"`, `"G[5, 10] p"`)
- `model_path`: Path to the PRISM model file

**Returns:**
- `True` if the formula is satisfied, `False` otherwise

### `entire_search_l1_batched(input_formula, model_path, horizon, max_workers=4, chunk_size=10)`
Performs an L1-distance-based search for counterexamples, processing batches in parallel.

**Parameters:**
- `input_formula`: MTL formula with parameterized intervals (e.g., `"F[t_1, t_2] p"`)
- `model_path`: Path to the PRISM model file
- `horizon`: Maximum time horizon
- `max_workers`: Number of parallel worker threads (default: 4)
- `chunk_size`: Number of formulas per batch (default: 10)

**Returns:**
- Minimum L1 distance to a counterexample, or `horizon` if no counterexample found

## Supported MTL Syntax

TempEST supports the following MTL operators:

- **Eventually with interval**: `F[a, b] φ` - φ holds at some time in [a, b]
- **Always with interval**: `G[a, b] φ` - φ holds at all times in [a, b]
- **Until with interval**: `U[a, b]` - standard until operator
- **Eventually with upper bound**: `F_<=n φ` - equivalent to `F[0, n] φ`
- **Eventually with strict upper bound**: `F_<n φ` - equivalent to `F[0, n-1] φ`
- **Always with upper bound**: `G_<=n φ` - equivalent to `G[0, n] φ`
- **Always with strict upper bound**: `G_<n φ` - equivalent to `G[0, n-1] φ`

Standard LTL operators (`&`, `|`, `!`, `X`, `U`) are also supported.

## Example Formulas

```python
# Eventually p holds between cycles 5 and 30
formula1 = "F[5, 30] p"

# Always q holds between cycles 1 and 10
formula2 = "G[1, 10] q"

# Eventually p within 20 cycles
formula3 = "F_<=20 p"

# Complex formula with conjunction
formula4 = "(F[1, 5] a) & (G[2, 8] b)"
```

## Parallel Processing

The `entire_search_l1_batched` function uses parallel processing to speed up model checking:

- Formulas are grouped by L1 distance
- Each distance group is divided into chunks
- Chunks are processed in parallel using `ThreadPoolExecutor`
- Early termination occurs when a counterexample is found

Adjust `max_workers` and `chunk_size` based on your system's capabilities and PRISM's performance.

## Troubleshooting

### PRISM Not Found
If you encounter errors about PRISM not being found:
1. Verify PRISM is installed correctly
2. Update `prism_path` in `tempest.py` to the correct location
3. Ensure PRISM executable has execute permissions

### Formula Parsing Errors
If MTL formulas fail to parse:
1. Verify the formula syntax matches supported MTL operators
2. Check that `mltl.lark` is in the same directory as `mltl2ltlf.py`
3. Ensure the `lark` Python package is installed

### Model Building Errors
If model building fails:
1. Verify `history` dictionary has consistent list lengths
2. Ensure `horizon` matches the length of trace lists
3. Check write permissions for `model_path`

## Citation

If you use TempEST in your research, please cite:

```bibtex
@software{tempest2026,
  title={{TempEST: Temporal Exploration for Stress Testing}},
  author={Katie Wang and Rory Lipkis and Anastasia Mavridou},
  year={2026},
  url={https://github.com/kwangel/TempEST}
}
```

**Note**: TempEST uses an adapted version of the [mltl2ltlf](https://github.com/lu-w/mltl2ltlf) library. If you use the MTL parsing functionality, please also consider citing the original work.

## License

This project is licensed under the MIT License.

## Contact

katiewang@berkeley.edu
