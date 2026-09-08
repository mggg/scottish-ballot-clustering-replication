# Examples

The [CLI pipeline example](run_cli_pipeline.sh) follows one three-candidate election using Borda
distance and two clusters. It starts a cast-ballot IP with PAM, converts the resulting SOL to JSON,
and uses the saved partition to start an all-ballot IP. Once both IPs have reached optimality and
saved their solutions, the script extracts, summarizes, and archives the results.

Run from the repository root with Bash and a working Gurobi license:

```sh
uv sync --locked
bash code/examples/run_cli_pipeline.sh
```

The script writes the outputs below to `example_results/` by default. For another run, supply a new
directory as its first argument. If a command fails, the script stops before later steps can consume
missing or stale output. You can also copy individual commands from the script to run only part of
the pipeline.

| Output                       | Contents                                                          |
| ---------------------------- | ----------------------------------------------------------------- |
| `IP_solutions/`, `logs/`     | Experiment-named SOL files and Gurobi logs.                       |
| `saved_solutions/`           | Both solutions as JSON, retaining centers and ballot memberships. |
| `extracted_solutions.csv`    | One row per SOL.                                                  |
| `election_and_clusters.json` | Election and all-ballot cluster statistics.                       |
| `solutions.zip`              | Both saved JSON files with loose copies retained.             |

## Direct Python use

To call the models from Python, start with [solve_integer_program.py](solve_integer_program.py),
which demonstrates all three model builders on a small synthetic profile. Using the same profile,
the companion [run_pam.py](run_pam.py) example demonstrates PAM without requiring a Gurobi license:

```sh
uv run python code/examples/solve_integer_program.py
uv run python code/examples/run_pam.py
```
