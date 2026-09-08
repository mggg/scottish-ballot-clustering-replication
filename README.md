# Scottish ballot clustering replication

This repository contains the data for [PAPER]() and Python code for reproducing the published
results. We provide three integer-program clustering models, weighted PAM, and tools for processing
solutions.

## Running an experiment

The code requires Python 3.13 and uses `uv` to manage its environment. To run an integer program,
you also need a Gurobi license valid on the machine doing the solve. From the repository root, sync
the environment and run an experiment:

```sh
uv sync --locked
uv run -m scottish_ballot_clustering coordinate \
  --file data/scot-elex/3_cands/eilean_siar_2022_ward3.csv \
  --run-type borda -k 2
```

To follow an election through the complete pipeline, run the CLI example. It includes warm starts,
JSON conversion, CSV extraction, summaries, and ZIP packaging:

```sh
bash code/examples/run_cli_pipeline.sh
```

The example keeps its outputs in `example_results/`, and the
[example guide](code/examples/README.md) explains those outputs and provides examples of calling
the models directly from Python. For individual command options, use the command's `--help`.

## Models and conventions

| Subcommand    | Centers                                                                   |
| ------------- | ------------------------------------------------------------------------- |
| `cast-ballot` | Distinct rankings actually cast, with each center assigned to itself.     |
| `all-ballot`  | Valid partial rankings, including rankings not cast in the election.      |
| `coordinate`  | Weighted coordinate medians, without ranking-consistency constraints.     |
| `pam`         | Cast ballots selected by weighted greedy BUILD and best-improvement SWAP. |

Although PAM uses the cast-ballot objective, its local-optimum status does not certify global
optimality.

All four methods weight distinct rankings by voter frequency and minimize weighted Manhattan
distance. The `--run-type` option determines how rankings are embedded: `borda` assigns scores `n-1,
n-2, ..., 0` by rank and zero to omitted candidates, while `head_to_head` uses one coordinate per
unordered candidate pair. Ranked candidates beat omitted candidates, and explicit ties between
ranked candidates are unsupported.

In the coordinate and all-ballot models, clusters may be empty and labels are ordered by the number
of distinct rankings assigned to them rather than voter weight. All-ballot centers may also be empty
rankings regardless of whether any ballots are assigned to that center.

## Results and reruns

By default, IP runs place solutions in top-level `IP_solutions/` and solver logs in `logs/`, both
grouped by `<model>/<k>_clusters/<candidate-folder>/`. Filenames include the election, metric,
model, and cluster count so they remain identifiable outside those directories. Use `--output-dir`
to change the output root or `--write-model` to add an MPS export beside the SOL file.

A SOL is saved only after Gurobi reports `OPTIMAL` within its configured tolerances. If Gurobi
returns without that status, the command fails and retains the log and any requested MPS even if a
feasible incumbent exists. When comparing runs, use separate output directories because
`--overwrite` removes the experiment's previous SOL, log, and MPS before starting the solver.

Because IP runs do not create summary statistics automatically, use the processing commands below to
produce them. PAM, by contrast, prints its medoids, memberships, objective, status, swap count, and
runtime as JSON to stdout.

## Warm starts

All three IP commands can start from a partition supplied by PAM or a saved cast-ballot solution. To
generate a partition from the loaded election, use `--pam-start`. Alternatively, load an individual
saved JSON or SOL file with `--warm-start path/to/cast_solution.json`.

The saved solution must use the same election, metric, and cluster count as the new run regardless
of its format. SOL files also require the original loader ordering because their assignments
identify ballots by index. We match JSON inputs by rankings and frequencies and check candidate
names and order before use. Once the partition is loaded, we prepare centers for the target model:

| Target        | Center preparation                                                                                 |
| ------------- | -------------------------------------------------------------------------------------------------- |
| `cast-ballot` | Choose a member minimizing weighted distance within each cluster (all clusters must be nonempty).  |
| `coordinate`  | Compute lower weighted coordinate medians.                                                         |
| `all-ballot`  | Solve one weighted 1-Kemeny problem per cluster under the selected Borda or head-to-head distance. |

When PAM supplies the partition, each ballot goes to the lowest-index nearest medoid on a tie except
that medoids are assigned to themselves. To satisfy the target model's symmetry constraints, centers
and cluster labels are reordered together where necessary.

For direct Python use, the loading and start-installation functions are in
[warm_start.py](code/scottish_ballot_clustering/warm_start.py).

## Processing solutions

Once you have a saved SOL, the analysis commands can convert it to JSON, collect SOL files into a
CSV, and summarize the election and its clusters. When supplying an election CSV, use the original
profile and loader ordering so the SOL's ballot indices can be interpreted correctly:

```sh
uv run python code/analysis_scripts/convert_solution.py result.sol \
  data/scot-elex/3_cands/eilean_siar_2022_ward3.csv result.json
uv run python code/analysis_scripts/extract_solutions.py IP_solutions extracted_solutions.csv
uv run python code/analysis_scripts/summarize_election.py \
  data/scot-elex/3_cands/eilean_siar_2022_ward3.csv --solution result.sol --top-n 5
```

Conversion retains empty clusters and preserves the saved assignments including how ties were
resolved. In the CSV export, each solution occupies one row with centers and assignments encoded as
JSON arrays. Both exports require new output files, while the summary command prints to stdout.

The [saved format documentation](docs/result-publication-format.md) explains how candidates and
clusters are represented and what the loader checks. For large collections, `iter_saved_solutions`
lets you process validated solutions one at a time from a ZIP, whereas `load_saved_solutions` loads
the entire collection into memory. The [collection guide](data/optimal_cluster_centers/README.md)
explains how to read and package archives.

## Batch runs

For SLURM runs, first create a manifest of the elections, metrics, and models to run. The manifest
contains absolute election paths, so generate it on the machine where those paths will be read. This
example selects seven-candidate elections and all six IP model/metric combinations at three
clusters:

```sh
uv run python code/hpc/make_jobs.py --n-candidates 7 -k 3 > jobs.tsv
bash code/hpc/submit_jobs.sh jobs.tsv --mem=256G --cpus-per-task=12
```

For other experiments, use the filters listed in `make_jobs.py --help`. The `--opt-type pam` filter,
for example, selects PAM under both metrics. Submission divides the manifest into arrays of at most
1,000 tasks, with each array depending on the previous one. `LP_CONCURRENT` sets the concurrency
limit, which defaults to 8. Depending on your cluster's memory, CPU, and job-array limits, you may
need to adjust these settings.

Remember to sync the environment before submitting jobs and keep `uv` and the Gurobi license
available on the compute nodes. Because the workers share that environment, leave the project
configuration and lockfile unchanged while they run.

## Platform notes

The command examples use Bash line continuations. In PowerShell or Command Prompt, write the Python
commands on one line. The batch scripts, however, require Bash, Unix utilities, and SLURM. Although
native Windows execution of the Python commands is expected to work, it has not been verified.

File replacement preserves ordinary Unix permission bits or the Windows read-only flag but not
ownership or access control lists. On Windows, read-only or open files may also prevent replacement
or cleanup, leaving temporary files when cleanup fails. See the documentation for
[chmod](https://docs.python.org/3.13/library/os.html#os.chmod) and [delete
sharing](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-deletefilew) for the
underlying platform behavior.

## Code and data

| Location                                                                | Contents                                                                 |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `code/scottish_ballot_clustering/`                                      | Model builders, metrics, loading, warm starts, and result processing.    |
| `code/analysis_scripts/`                                                | Standalone commands for conversion, extraction, summaries, and archives. |
| [code/examples/](code/examples/README.md)                               | CLI pipeline and direct Python examples.                                 |
| `code/hpc/`                                                             | Job manifests, the batch model runner, and SLURM scripts.                |
| `code/tests/`                                                           | Model and workflow checks.                                               |
| [data/scot-elex/](data/scot-elex/README.md)                             | Election CSVs, provenance, and format.                                   |
| [data/optimal_cluster_centers/](data/optimal_cluster_centers/README.md) | Published solution ZIPs.                                                 |
| [reports/](reports/README.md)                                           | Warm-start measurements and comparisons.                                 |

Import model builders and enums from `scottish_ballot_clustering.models`. The package keeps reusable
computation separate from the analysis commands and batch scripts, but all three use the shared
environment defined by `pyproject.toml` and `uv.lock`.

## Verification

Run the test suite with:

```sh
uv run pytest
```

The suite requires a Gurobi license and checks model objectives against small exhaustive cases, warm
starts, result conversion, summaries, overwrite protection, and batch argument forwarding. It does
not rerun the full election collection. For PAM alone, you can run the tests without a license:

```sh
uv run pytest code/tests/test_pam.py
```
