"""Locate experiment artifacts in the solution and log directories."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentPaths:
    """Hold artifact destinations sharing one descriptive experiment name.

    Paths describe integer-program destinations, not existing files. PAM prints its result to
    standard output and does not write these artifacts.

    Attributes:
        solution (Path): Integer-program SOL destination under IP_solutions.
        log (Path): Gurobi log destination under logs.
        model (Path): Optional MPS destination beside the SOL file.
    """

    solution: Path
    log: Path
    model: Path


def build_experiment_paths(
    input_file: Path, run_type: str, opt_type: str, n_clusters: int, output_dir: Path = Path(".")
) -> ExperimentPaths:
    """Derive artifact paths without reading or creating files.

    Args:
        input_file (Path): Election CSV; its stem identifies the election and its parent identifies
            the candidate-count folder.
        run_type (str): Embedding name, borda or head_to_head.
        opt_type (str): Model family, cast_ballot, all_ballot, coordinate, or pam.
        n_clusters (int): Positive cluster count.
        output_dir (Path): Root containing IP_solutions and logs; default current directory.

    Returns:
        ExperimentPaths: Destinations grouped by model family, cluster count, and candidate folder.
        Filenames retain the election, embedding, method, and cluster count when copied elsewhere.
        Inputs are assumed to follow the model CLI's naming and validation contracts.
    """
    method = "pam" if opt_type == "pam" else f"ip_{opt_type}"
    name = f"{input_file.stem}_{run_type}_{method}__NCLUST_{n_clusters}"
    group = Path(opt_type) / f"{n_clusters}_clusters" / input_file.parent.name
    solutions = output_dir / "IP_solutions" / group

    return ExperimentPaths(
        solution=solutions / f"{name}_solution.sol",
        log=output_dir / "logs" / group / f"{name}_solver.log",
        model=solutions / f"{name}_model.mps",
    )


def prepare_artifact_directories(paths: ExperimentPaths, *, overwrite: bool = False) -> None:
    """Create artifact directories, removing the previous experiment's files when requested.

    Args:
        paths (ExperimentPaths): SOL, log, and MPS destinations for one experiment.
        overwrite (bool): Remove all matching artifacts, including those a new run may not produce.

    Returns:
        None: Prepare writable directories without creating output files.

    Raises:
        FileExistsError: If any artifact exists and overwrite is false.
        OSError: If artifact removal or directory creation fails.
    """
    for path in (paths.solution, paths.log, paths.model):
        if path.exists() and not overwrite:
            raise FileExistsError(
                f"Experiment output already exists: {path}. Use --overwrite to replace it."
            )

        if overwrite:
            path.unlink(missing_ok=True)

    paths.solution.parent.mkdir(parents=True, exist_ok=True)
    paths.log.parent.mkdir(parents=True, exist_ok=True)
