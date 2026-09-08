"""Run integer programming or PAM for an election, metric, and cluster count."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal

import click
import gurobipy as gp
import numpy as np
from numpy.typing import NDArray

from .experiment_paths import ExperimentPaths, build_experiment_paths, prepare_artifact_directories
from .load_election import load_election
from .metrics import ballot_borda_vector, ballot_hh_vector, pairwise_manhattan
from .models import (
    AllBallotModelName,
    CastBallotModelName,
    CoordinateModelName,
    build_all_ballot_model,
    build_cast_ballot_model,
    build_coordinate_model,
)
from .pam import PAMResult, pam
from .warm_start import (
    apply_pam_warm_start,
    apply_warm_start,
    load_starting_assignments,
)


@dataclass(frozen=True)
class ElectionInputs:
    """Loaded ballots and frequencies with a resolved metric and valid cluster count."""

    run_type: Literal["borda", "head_to_head"]
    n_clusters: int
    candidates: list[str]
    ballots: list[tuple[int, ...]]
    weights: NDArray[np.int64]


@dataclass(frozen=True)
class IPRequest:
    """Select an IP family with an optional partition or PAM medoid start."""

    family: Literal["cast_ballot", "coordinate", "all_ballot"]
    starting_assignments: list[int] | None = None
    pam_medoids: list[int] | None = None


def build_model(
    ballots: Sequence[Sequence[int]],
    weights: NDArray,
    n_candidates: int,
    run_type: str,
    opt_type: str,
    n_clusters: int,
) -> gp.Model:
    """Build an unsolved clustering model from indexed ballots and frequencies.

    Embeddings use a common candidate indexing and Manhattan distance. Cast-ballot construction
    allocates a square distance matrix; the other families use coordinate variables directly. Input
    rankings and frequencies should satisfy load_election's contract. Only the cluster-count range
    is checked before embedding the ballots.

    Args:
        ballots (list[tuple[int, ...]]): Distinct partial rankings in preference order, using
            zero-based candidate indices.
        weights (NDArray): Positive integer-valued frequencies of shape ``(len(ballots),)``.
        n_candidates (int): Positive total number of candidates.
        run_type (str): Metric name: "borda" or "head_to_head".
        opt_type (str): Center family: "cast_ballot", "all_ballot", or "coordinate".
        n_clusters (int): Number of clusters, between 1 and len(ballots), inclusive.

    Returns:
        gurobipy.Model: An unsolved model with its objective and constraints installed. The caller
        owns the model and must dispose of it when finished.

    Raises:
        ValueError: If the cluster count is outside the allowed range or the selected embedding or
            model builder rejects the input values.
        KeyError: If run_type or opt_type is not recognized.
        gurobipy.GurobiError: If Gurobi cannot initialize or construct the model.
    """
    if not 1 <= n_clusters <= len(ballots):
        raise ValueError("Cluster count must be between 1 and the number of distinct ballots")

    embedding = {"borda": ballot_borda_vector, "head_to_head": ballot_hh_vector}[run_type]
    coordinates = np.array(
        [embedding(ballot=list(ballot), n_candidates=n_candidates) for ballot in ballots]
    )
    metric = "BORDA" if run_type == "borda" else "HEAD_TO_HEAD"

    if opt_type == "cast_ballot":
        return build_cast_ballot_model(
            model_name=CastBallotModelName[metric],
            n_ballots=len(ballots),
            weight_vector=weights,
            cost_matrix=pairwise_manhattan(coordinates),
            n_clusters=n_clusters,
        )

    builder, names = {
        "all_ballot": (build_all_ballot_model, AllBallotModelName),
        "coordinate": (build_coordinate_model, CoordinateModelName),
    }[opt_type]

    return builder(
        model_name=names[metric],
        ballots_as_coordinates_array=coordinates,
        weight_vector=weights,
        value_vector=np.arange(n_candidates) if run_type == "borda" else np.array([-1, 0, 1]),
        n_candidates=n_candidates,
        n_clusters=n_clusters,
    )


def run_election(
    input_file: Path,
    run_type: str,
    opt_type: str,
    n_clusters: int = 2,
    output_dir: Path = Path("."),
    time_limit: float | None = None,
    threads: int | None = None,
    write_model: bool = False,
    max_iter: int = 300,
    overwrite: bool = False,
    warm_start: Path | None = None,
    pam_start: bool = False,
) -> None:
    """Cluster weighted ballots with integer programming or PAM and write the results.

    Artifacts are grouped under IP_solutions and logs with descriptive experiment names.
    Existing experiment output is refused unless overwrite is enabled. Overwriting removes the
    matching SOL, log, and MPS before solving, including artifacts the new run may not produce.
    A SOL file is saved only when Gurobi establishes optimality within its configured tolerances.
    PAM prints its clustering result to standard output. No per-run summary file is produced.

    Args:
        input_file (Path): Scottish election CSV file to load.
        run_type (str): Metric name: "borda" or "head_to_head".
        opt_type (str): Method: "cast_ballot", "all_ballot", "coordinate", or "pam".
        n_clusters (int): Number of clusters, between 1 and the distinct ballot count.
        output_dir (Path): Root containing IP_solutions and logs; default current directory.
        time_limit (float | None): Positive limit in seconds for Gurobi optimization or PAM SWAP,
            excluding model construction, PAM BUILD, and output. The all-ballot warm-start
            preparation solve receives a separate limit of the same duration. Automatic PAM
            preparation is excluded from this limit. None is unlimited.
        threads (int | None): Positive Gurobi thread limit, or None for its default. Unused by PAM.
        write_model (bool): Export a named MPS file before optimization. Unsupported by PAM.
        max_iter (int): Nonnegative maximum number of accepted PAM swaps; unused by IP models.
        overwrite (bool): Remove existing artifacts for this IP experiment before rerunning.
            Defaults to False; unused by PAM.
        warm_start (Path | None): Cast-ballot SOL or saved-solution JSON for the same election,
            metric, and cluster count. SOL requires the original ballot ordering; JSON matches
            stored rankings and weights. Supported by all IP families; cast-ballot targets require
            every starting cluster to be nonempty.
        pam_start (bool): Run PAM on the loaded profile before building the IP, using at most 300
            accepted swaps and no time limit. Supported by all IP families; mutually exclusive
            with warm_start. Defaults to False.

    Returns:
        None: IP artifacts are saved and their solution path is printed; PAM prints its result.

    Raises:
        click.ClickException: If experiment output exists without overwrite, input validation fails,
            PAM export is requested, file access or model construction fails, or IP optimality
            is not established. A failed IP run may leave partial artifacts.
        pandas.errors.EmptyDataError: If the input CSV file is empty.
        pandas.errors.DataError: If the loader rejects election metadata or candidate records.
    """
    if opt_type == "pam" and write_model:
        raise click.ClickException("PAM has no integer-program model to export")

    if warm_start is not None and opt_type not in ("cast_ballot", "coordinate", "all_ballot"):
        raise click.ClickException("Warm starts require an integer-program target")

    if pam_start and (opt_type == "pam" or warm_start is not None):
        raise click.ClickException("Use only one starting solution, with an integer-program target")

    try:
        inputs = _load_election_inputs(input_file, run_type, n_clusters)
        if opt_type == "pam":
            result = _solve_pam(inputs, max_iter, time_limit)
            click.echo(json.dumps(result, indent=2))
            return

        request = _load_ip_request(opt_type, warm_start, inputs, pam_start)
        paths = build_experiment_paths(input_file, run_type, opt_type, n_clusters, output_dir)
        prepare_artifact_directories(paths, overwrite=overwrite)
        _solve_integer_program(inputs, request, paths, time_limit, threads, write_model)
    except (gp.GurobiError, ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc


def _load_election_inputs(input_file: Path, run_type: str, n_clusters: int) -> ElectionInputs:
    """Load and validate the profile and metric before preparing any output artifacts.

    Args:
        input_file (Path): Original Scottish election CSV.
        run_type (str): Borda or head-to-head metric name.
        n_clusters (int): Cluster count between one and the number of distinct ballots.

    Returns:
        ElectionInputs: Ballots, frequencies, candidate order, and resolved experiment dimensions.

    Raises:
        ValueError: If the metric, cluster count, or election profile is invalid.
        OSError: If the CSV cannot be read.
    """
    ballots, weights, candidates = load_election(input_file)
    if not 1 <= n_clusters <= len(ballots):
        raise ValueError("Cluster count exceeds the number of distinct ballots")
    if run_type not in ("borda", "head_to_head"):
        raise ValueError(f"Unsupported metric: {run_type}")

    metric: Literal["borda", "head_to_head"] = "borda" if run_type == "borda" else "head_to_head"
    return ElectionInputs(metric, n_clusters, candidates, ballots, weights)


def _load_ip_request(
    family: str, warm_start: Path | None, inputs: ElectionInputs, pam_start: bool = False
) -> IPRequest:
    """Resolve an IP family and prepare a partition from a saved solution or an in-memory PAM run.

    Args:
        family (str): Cast-ballot, coordinate, or all-ballot model family.
        warm_start (Path | None): Compatible cast-ballot SOL or saved-solution JSON, or None.
        inputs (ElectionInputs): Validated target profile and metric.
        pam_start (bool): Run PAM with at most 300 accepted swaps and no time limit, using the
            target profile, metric, and cluster count. Mutually exclusive with a saved start.

    Returns:
        IPRequest: Model selection with validated starting labels or medoid indices.

    Raises:
        ValueError: If the family is unsupported or the starting solution is incompatible.
        OSError: If a starting solution cannot be read.
    """
    if family not in ("cast_ballot", "coordinate", "all_ballot"):
        raise ValueError(f"Unsupported integer-program family: {family}")
    if warm_start is not None and pam_start:
        raise ValueError("Use only one starting solution")

    assignments = None
    if warm_start is not None:
        assignments = load_starting_assignments(
            warm_start,
            inputs.ballots,
            inputs.weights,
            inputs.candidates,
            inputs.run_type,
            inputs.n_clusters,
        )
        if family == "cast_ballot" and set(assignments) != set(range(inputs.n_clusters)):
            raise ValueError("Cast-ballot warm starts require nonempty clusters")

    medoids = None
    if pam_start:
        medoids = _solve_pam(inputs, max_iter=300, time_limit=None)["medoid_indices"]

    return IPRequest(family, assignments, medoids)


def _election_coordinates(inputs: ElectionInputs) -> NDArray:
    """Embed the loaded ballots in their existing candidate and ballot order.

    Args:
        inputs (ElectionInputs): Validated profile and metric.

    Returns:
        NDArray: Shape (n_ballots, n_coordinates) with integer coordinates for each distinct
    """
    embedding = {"borda": ballot_borda_vector, "head_to_head": ballot_hh_vector}[inputs.run_type]
    return np.array(
        [embedding(ballot=b, n_candidates=len(inputs.candidates)) for b in inputs.ballots]
    )


def _solve_pam(inputs: ElectionInputs, max_iter: int, time_limit: float | None) -> PAMResult:
    """Run PAM on the loaded profile and return its clustering result.

    Args:
        inputs (ElectionInputs): Validated profile, embedding name, and cluster count.
        max_iter (int): Nonnegative maximum accepted swaps.
        time_limit (float | None): Positive SWAP limit in seconds, or None for no time limit.

    Returns:
        PAMResult: Medoids, membership weights, objective, and termination information. No files
        are written and the input profile is not modified.

    Raises:
        ValueError: If PAM rejects the profile or search limits.
    """
    return pam(
        _election_coordinates(inputs),
        np.array(inputs.weights),
        inputs.n_clusters,
        max_iter=max_iter,
        time_limit=time_limit,
    )


def _solve_integer_program(
    inputs: ElectionInputs,
    request: IPRequest,
    paths: ExperimentPaths,
    time_limit: float | None,
    threads: int | None,
    write_model: bool,
) -> None:
    """Optimize an IP and save solver artifacts before disposing of the model.

    Args:
        inputs (ElectionInputs): Validated profile, embedding, and cluster count.
        request (IPRequest): Selected family and any compatible starting partition.
        paths (ExperimentPaths): Artifact destinations with existing parent directories.
        time_limit (float | None): Positive optimization limit, or None for the solver default.
        threads (int | None): Positive Gurobi thread limit, or None for the solver default.
        write_model (bool): Whether to export MPS before optimization.

    Returns:
        None: Save the optimal solution and print its path. Solver status and runtime remain
        in the solver log. Any status other than GRB.OPTIMAL produces no SOL file.

    Raises:
        click.ClickException: If optimization finishes without establishing optimality.
        gurobipy.GurobiError: If model construction, optimization, or artifact writing fails.
        ValueError: If model construction rejects the profile.
        KeyError: If model selection or required metadata is invalid.
    """
    with build_model(
        inputs.ballots,
        np.array(inputs.weights),
        len(inputs.candidates),
        inputs.run_type,
        request.family,
        inputs.n_clusters,
    ) as model:
        model.Params.LogFile = str(paths.log)

        if time_limit is not None:
            model.Params.TimeLimit = time_limit

        if threads is not None:
            model.Params.Threads = threads

        if request.pam_medoids is not None:
            apply_pam_warm_start(
                model,
                request.pam_medoids,
                _election_coordinates(inputs),
                inputs.weights,
                inputs.n_clusters,
            )
        elif request.starting_assignments is not None:
            apply_warm_start(
                model,
                request.starting_assignments,
                _election_coordinates(inputs),
                inputs.weights,
                inputs.n_clusters,
            )

        if write_model:
            model.write(str(paths.model))

        model.optimize()

        if model.Status != gp.GRB.OPTIMAL:
            raise click.ClickException(
                f"Optimality was not established (status {model.Status}); no SOL file saved"
            )

        model.write(str(paths.solution))
        click.echo(f"Solution: {paths.solution}")


def build_model_command(opt_type: str) -> click.Command:
    """Construct a model command with only its applicable experiment options.

    Args:
        opt_type (str): Model family: cast_ballot, all_ballot, coordinate, or pam.

    Returns:
        click.Command: Command calling run_election with the selected family. HPC callers can
        append runtime options before invoking the command.

    Raises:
        KeyError: If opt_type is not a supported model family.
    """
    descriptions = {
        "cast_ballot": "Choose centers from cast ballots using an integer program.",
        "all_ballot": "Choose consistent partial-ranking centers using an integer program.",
        "coordinate": "Choose independent coordinate centers using an integer program.",
        "pam": "Choose cast-ballot medoids using weighted PAM BUILD and SWAP.",
    }
    description = descriptions[opt_type]
    params: list[click.Parameter] = [
        click.Option(
            ["--file", "input_file"],
            required=True,
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            help="Scottish election CSV containing ranked ballots and their frequencies.",
        ),
        click.Option(
            ["--run-type"],
            required=True,
            type=click.Choice(["borda", "head_to_head"]),
            help="Ballot embedding for Manhattan distance: pessimistic Borda or pairwise comparisons.",
        ),
        click.Option(
            ["--n-clusters", "-k"],
            type=click.IntRange(min=1),
            default=2,
            show_default=True,
            help="Number of cluster centers, at most the number of distinct cast ballots.",
        ),
    ]

    if opt_type == "pam":
        params.append(
            click.Option(
                ["--max-iter"],
                type=click.IntRange(min=0),
                default=300,
                show_default=True,
                help="Maximum accepted PAM swaps; 0 returns the BUILD initialization.",
            )
        )
    else:
        params.append(
            click.Option(
                ["--output-dir"],
                type=click.Path(file_okay=False, path_type=Path),
                default=".",
                help="Root containing IP_solutions and logs.",
                show_default=True,
            )
        )
        params.append(
            click.Option(
                ["--write-model"], is_flag=True, help="Also save the integer program as MPS."
            )
        )
        params.append(
            click.Option(
                ["--overwrite"],
                is_flag=True,
                help="Remove this experiment's existing SOL, log, and MPS files before rerunning.",
            )
        )

    if opt_type != "pam":
        params.append(
            click.Option(
                ["--pam-start"],
                is_flag=True,
                help="Run PAM first on this election, metric, and cluster count, then use its "
                "centers as a warm start. Uses at most 300 accepted swaps, outside the IP time "
                "limit. Cannot be combined with --warm-start.",
            )
        )

    if opt_type != "pam":
        params.append(
            click.Option(
                ["--warm-start"],
                type=click.Path(exists=True, dir_okay=False, path_type=Path),
                help="Start from a cast-ballot SOL or saved-solution JSON for the same election, "
                "metric, and cluster count. SOL requires the original ballot ordering; JSON "
                "matches rankings and weights. Cannot be combined with --pam-start.",
            )
        )

    return click.Command(
        opt_type.replace("_", "-"),
        params=params,
        callback=partial(run_election, opt_type=opt_type),
        help=description
        + (
            " Results are printed as JSON to standard output."
            if opt_type == "pam"
            else " A SOL file is saved only when Gurobi establishes optimality. "
            "Existing experiment artifacts require --overwrite to replace."
        ),
    )


def create_cli() -> click.Group:
    """Build an independent command registry for the model CLI.

    Returns:
        click.Group: Fresh model commands with no shared mutable option lists.
    """
    group = click.Group(help="Cluster election ballots. Choose a model for its options and help.")

    for family in ("cast_ballot", "all_ballot", "coordinate", "pam"):
        group.add_command(build_model_command(family))

    return group


main = create_cli()
