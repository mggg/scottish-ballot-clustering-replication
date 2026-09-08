# Code

This directory separates the reusable clustering package from the scripts for running experiments
and processing their results. Run the commands below from the repository root so their data and
output paths resolve correctly. Before starting, sync the shared environment:

```sh
uv sync --locked
```

The [main README](../README.md) covers installation, model options, and output conventions.

## scottish_ballot_clustering/

The [Python package](scottish_ballot_clustering/) contains the integer-program models, weighted PAM,
ballot metrics, election loader, warm-start preparation, and result-processing functions. Its CLI
groups the models into subcommands, each with its own options and help:

```sh
uv run -m scottish_ballot_clustering coordinate --help
```

For direct Python use, import builders and model-name enums from
`scottish_ballot_clustering.models`. The builders return Gurobi models, so you can set parameters or
add constraints before calling `optimize()`. IP solving requires a Gurobi license, while PAM can run
without one.

## analysis_scripts/

The [analysis scripts](analysis_scripts/) convert SOL files to saved JSON, extract solutions into
CSV, summarize elections and clusters, and package or reconstruct saved solutions. Each script is
run independently and documents its arguments through `--help`:

```sh
uv run python code/analysis_scripts/convert_solution.py --help
```

These commands do not require a Gurobi license. When converting a SOL, supply its original election
CSV so ballot indices can be interpreted correctly. Conversion preserves the solver's assignments,
whereas reconstruction from centers can assign tied ballots differently. The
[saved-solution format](../docs/result-publication-format.md) explains the resulting JSON.

## examples/

Start with the [examples](examples/README.md) to see how the pieces fit together. The CLI pipeline
runs one election through warm starts, solving, conversion, summaries, and ZIP packaging:

```sh
bash code/examples/run_cli_pipeline.sh
```

The script writes to `example_results/` by default. Supply a new output directory as its first
argument for another run. For smaller examples of the Python API, `solve_integer_program.py` and
`run_pam.py` use the same synthetic profile to demonstrate the model builders and PAM directly.

## hpc/

The [HPC scripts](hpc/) run batches of experiments through SLURM. Create a manifest with
`make_jobs.py`, then pass it to `submit_jobs.sh` to submit the experiments as job arrays. The
[batch instructions](../README.md#batch-runs) give the commands and resource options.

Before submission, sync the environment and check that the manifest's election paths are accessible
on the compute nodes. Keep the shared environment unchanged while jobs run, and choose memory, CPU,
and concurrency settings appropriate to your cluster. Submission requires Bash and SLURM.

## tests/

The [test suite](tests/) checks model objectives against small exhaustive cases and exercises warm
starts, result conversion, summaries, and archives. It verifies these behaviors without rerunning
the full election collection:

```sh
uv run pytest
```

The full suite requires a Gurobi license. To check PAM alone without one, run
`uv run pytest code/tests/test_pam.py`.
