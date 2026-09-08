"""Extract integer-program solutions and recover their weighted ballot clusters."""

import csv
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike

from .load_election import validate_profile
from .solution_types import (
    BallotCluster,
    BallotMemberships,
    ExtractedSolution,
    PairedBallotClusters,
    SolutionMetadata,
)


def extract_solution(path: str | Path) -> ExtractedSolution:
    """Extract centers and assignments from one complete Gurobi SOL file.

    Args:
        path (str | Path): Text SOL file, including zero-valued assignment and center indicators.

    Returns:
        ExtractedSolution: JSON-compatible source path, model name, objective, center kind, centers,
        and assignments. Each assignment is a zero-based cluster index in ballot order. Cast-ballot
        centers are ballot indices in ascending order; other centers are coordinate vectors in
        model cluster order. Empty clusters remain in centers.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If headers, numeric values, or required indicator structure are invalid, or the
            model name is unsupported.
    """
    path = Path(path)

    with path.open(encoding="utf-8") as source:
        model, objective, variables = _parse_sol(source)

    metadata: SolutionMetadata = {
        "source": str(path.resolve()),
        "model": model,
        "objective": objective,
    }
    if model.startswith("cast_ballot_"):
        centers, assignments = _extract_cast_ballot_clusters(variables)
        return {
            **metadata,
            "center_kind": "ballot_index",
            "centers": centers,
            "assignments": assignments,
        }

    # Coordinate and all-ballot models share the same center and assignment encoding.
    coordinate_centers, assignments = _extract_coordinate_encoded_clusters(variables, model)
    return {
        **metadata,
        "center_kind": "coordinates",
        "centers": coordinate_centers,
        "assignments": assignments,
    }


def _parse_sol(lines: Iterable[str]) -> tuple[str, float, dict[str, float]]:
    """Parse SOL headers and finite variable values without accessing the filesystem.

    Args:
        lines (Iterable[str]): Complete text SOL contents, including comments and blank lines.

    Returns:
        tuple[str, float, dict[str, float]]: Supported model name, reported objective, and variable
        values keyed by their exact names. Unknown auxiliary variables are retained for parsing.

    Raises:
        ValueError: If headers are missing, repeated, or unsupported, or a variable is repeated,
            malformed, or nonfinite.
    """
    model: str | None = None
    objective: float | None = None
    variables = {}

    for line_number, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        if line.startswith("# Solution for model "):
            if model is not None:
                raise ValueError("Repeated model header")

            model = line.removeprefix("# Solution for model ")
        elif line.startswith("# Objective value = "):
            if objective is not None:
                raise ValueError("Repeated objective header")

            objective = float(line.removeprefix("# Objective value = "))
        elif not line.startswith("#"):
            name, value = _parse_sol_variable(line, line_number)
            if name in variables:
                raise ValueError(f"Malformed or repeated variable at line {line_number}")

            variables[name] = value

    families = ("cast_ballot", "coordinate", "all_ballot")
    metrics = ("borda_pessimistic", "head_to_head")
    supported = {f"{family}_{metric}" for family in families for metric in metrics}

    if model is None or model not in supported or objective is None or not math.isfinite(objective):
        raise ValueError("Missing or unsupported model header, or invalid objective header")

    return model, objective, variables


def _parse_sol_variable(line: str, line_number: int) -> tuple[str, float]:
    """Parse one variable name and finite value from a SOL data line.

    Args:
        line (str): Non-comment SOL line stripped of surrounding whitespace.
        line_number (int): One-based source line number for error messages.

    Returns:
        tuple[str, float]: Variable name and finite numeric value.

    Raises:
        ValueError: If the line has the wrong field count or the value is invalid or nonfinite.
    """
    fields = line.split()
    if len(fields) != 2:
        raise ValueError(f"Malformed or repeated variable at line {line_number}")

    name, raw_value = fields
    value = float(raw_value)
    if not math.isfinite(value):
        raise ValueError(f"Nonfinite variable at line {line_number}")

    return name, value


def _binary_indicators(
    variables: Mapping[str, float], prefix: str, arity: int
) -> dict[tuple[int, ...], bool]:
    """Decode one indexed binary variable family with the solver's numeric tolerance.

    Args:
        variables (Mapping): Variable names mapped to finite numeric values.
        prefix (str): Exact variable family name preceding the brackets.
        arity (int): Required number of integer indices.

    Returns:
        dict: Index tuples mapped to booleans. Values within 1e-5 of zero or one are accepted.

    Raises:
        ValueError: If a matching variable has invalid or repeated indices, or is nonbinary.
    """
    indicators = {}

    for name, value in variables.items():
        match = re.fullmatch(r"(\w+)\[(-?\d+(?:,-?\d+)*)\]", name)

        if not match or match[1] != prefix:
            continue

        indices = tuple(map(int, match[2].split(",")))

        if len(indices) != arity or indices in indicators:
            raise ValueError(f"Invalid or repeated indicator indices: {name}")

        if min(abs(value), abs(value - 1)) > 1e-5:
            raise ValueError(f"Nonbinary indicator: {name}")

        indicators[indices] = value > 0.5

    return indicators


def _assignment_dimensions(indicators: Mapping[tuple[int, ...], bool]) -> tuple[int, int]:
    """Validate a complete ballot-by-center assignment array and return its dimensions.

    Args:
        indicators (Mapping): Binary values keyed by nonnegative (ballot, center) indices.

    Returns:
        tuple[int, int]: Positive ballot count and number of possible centers.

    Raises:
        ValueError: If the array is empty, has negative indices, or has missing cells.
    """
    if not indicators or any(min(key) < 0 for key in indicators):
        raise ValueError("Missing or invalid assignment indicators")

    n_ballots = max(ballot for ballot, _ in indicators) + 1
    n_centers = max(center for _, center in indicators) + 1

    if len(indicators) != n_ballots * n_centers:
        raise ValueError("Assignment indicators must form a complete rectangular array")

    return n_ballots, n_centers


def _assigned_clusters(
    indicators: Mapping[tuple[int, ...], bool], n_ballots: int, labels: Mapping[int, int]
) -> list[int]:
    """Resolve each ballot's selected center to a dense cluster label.

    Args:
        indicators (Mapping): Complete binary assignment array keyed by (ballot, center).
        n_ballots (int): Number of ballots in the array.
        labels (Mapping): Selected center indices mapped to output cluster indices.

    Returns:
        list[int]: Exactly one cluster label per ballot, in ballot order.

    Raises:
        ValueError: If a ballot selects zero or multiple centers, or selects an inactive center.
    """
    assignments: dict[int, int] = {}

    for (ballot, center), selected in indicators.items():
        if not selected:
            continue

        if ballot in assignments or center not in labels:
            raise ValueError("Each ballot must be assigned to exactly one selected center")

        assignments[ballot] = labels[center]

    if assignments.keys() != set(range(n_ballots)):
        raise ValueError("Each ballot must be assigned to exactly one selected center")

    return [assignments[ballot] for ballot in range(n_ballots)]


def _extract_cast_ballot_clusters(variables: Mapping[str, float]) -> tuple[list[int], list[int]]:
    """Interpret cast-ballot centers and their center-first assignment indices.

    Args:
        variables (Mapping): Finite numeric values from a parsed cast-ballot SOL file.

    Returns:
        tuple[list[int], list[int]]: Selected ballot indices in ascending order and dense cluster
        labels in ballot order.

    Raises:
        ValueError: If indicators are incomplete, assignments are invalid, or a center does not
            own its ballot.
    """
    center_indicators = _binary_indicators(variables, "centroid_indicator", 1)
    raw_assignments = _binary_indicators(variables, "cluster_assignment", 2)
    assignment_indicators = {
        (ballot, center): value for (center, ballot), value in raw_assignments.items()
    }
    n_ballots, n_centers = _assignment_dimensions(assignment_indicators)

    if n_centers != n_ballots or center_indicators.keys() != {(j,) for j in range(n_ballots)}:
        raise ValueError("Missing or invalid cast-ballot center indicators")

    centers = [j for j in range(n_ballots) if center_indicators[j,]]
    labels = {ballot: cluster for cluster, ballot in enumerate(centers)}
    assignments = _assigned_clusters(assignment_indicators, n_ballots, labels)

    if any(assignments[ballot] != cluster for cluster, ballot in enumerate(centers)):
        raise ValueError("Cast-ballot centers must be assigned to themselves")

    return centers, assignments


def _coordinate_centers(
    indicators: Mapping[tuple[int, ...], bool], n_clusters: int, model: str
) -> list[list[int]]:
    """Recover one selected value per center coordinate, retaining empty clusters.

    Args:
        indicators (Mapping): Binary values keyed by (coordinate, cluster, value).
        n_clusters (int): Number of labeled clusters in the assignment array.
        model (str): Supported coordinate or all-ballot model name.

    Returns:
        list[list[int]]: Center vectors in cluster order, with coordinates in index order.

    Raises:
        ValueError: If indicator dimensions, allowed values, or coordinate selections are invalid.
    """
    if not indicators or any(i < 0 or not 0 <= r < n_clusters for i, r, v in indicators):
        raise ValueError("Missing or invalid coordinate center indicators")

    dimension = max(i for i, r, v in indicators) + 1
    values = {v for i, r, v in indicators}
    allowed = {-1, 0, 1} if model.endswith("head_to_head") else set(range(dimension))

    if not values <= allowed:
        raise ValueError("Center values are outside the embedding range")

    if len(indicators) != dimension * n_clusters * len(values):
        raise ValueError("Incomplete coordinate center indicators")

    selected_values: dict[tuple[int, int], int] = {}

    for (coordinate, cluster, value), selected in indicators.items():
        if not selected:
            continue

        if (cluster, coordinate) in selected_values:
            raise ValueError("Each center coordinate must select exactly one value")

        selected_values[cluster, coordinate] = value

    if len(selected_values) != n_clusters * dimension:
        raise ValueError("Each center coordinate must select exactly one value")

    return [[selected_values[r, i] for i in range(dimension)] for r in range(n_clusters)]


def _extract_coordinate_encoded_clusters(
    variables: Mapping[str, float], model: str
) -> tuple[list[list[int]], list[int]]:
    """Interpret the shared coordinate and all-ballot solution layout.

    Args:
        variables (Mapping): Finite numeric values from a parsed SOL file.
        model (str): Supported coordinate or all-ballot model name.

    Returns:
        tuple[list, list[int]]: Center vectors and dense cluster labels in ballot order.

    Raises:
        ValueError: If center or assignment indicators are incomplete or inconsistent.
    """
    assignment_indicators = _binary_indicators(variables, "ballot_j_to_cluster_r_indicator", 2)
    center_indicators = _binary_indicators(variables, "coord_i_in_centroid_r_is_v", 3)
    n_ballots, n_clusters = _assignment_dimensions(assignment_indicators)

    centers = _coordinate_centers(center_indicators, n_clusters, model)
    labels = {cluster: cluster for cluster in range(n_clusters)}
    assignments = _assigned_clusters(assignment_indicators, n_ballots, labels)

    return centers, assignments


def rebuild_clusters(
    solution: ExtractedSolution,
    ballots: Sequence[Sequence[int]],
    weights: ArrayLike,
    candidates: Sequence[str],
) -> list[BallotCluster]:
    """Recover weighted ballot clusters from the election's indexed profile.

    Order matters, so supply the same ballot and candidate ordering used to build the model.
    Coordinate centers remain vectors because arbitrary coordinate medians need not encode valid
    rankings.

    Args:
        solution (ExtractedSolution): Unmodified result of extract_solution.
        ballots (Sequence[Sequence[int]]): Indexed rankings in model ballot order.
        weights (ArrayLike): Ballot frequencies in the same order.
        candidates (Sequence[str]): Labels in model candidate order.

    Returns:
        list[BallotCluster]: Clusters in center order, including empty clusters. Each contains
        cluster_index, center, ballot_indices, ballots, weights, and candidates. Cast-ballot centers
        are rankings; coordinate centers are vectors, as identified by center_kind in each cluster.

    Raises:
        KeyError: If a required solution field is absent.
        ValueError: If profile data, dimensions, or cluster labels are invalid.
    """
    validate_solution_profile(solution, ballots, weights, candidates)
    frequencies = np.asarray(weights, dtype=float)
    assignments = solution["assignments"]

    clusters: list[BallotCluster] = []

    for r in range(len(solution["centers"])):
        center = (
            list(ballots[solution["centers"][r]])
            if solution["center_kind"] == "ballot_index"
            else solution["centers"][r]
        )
        indices = [j for j, label in enumerate(assignments) if label == r]
        clusters.append(
            {
                "cluster_index": r,
                "center_kind": "ranking"
                if solution["center_kind"] == "ballot_index"
                else "coordinates",
                "center": list(center),
                "ballot_indices": indices,
                "ballots": [list(ballots[j]) for j in indices],
                "weights": [float(frequencies[j]) for j in indices],
                "candidates": list(candidates),
            }
        )

    return clusters


def validate_solution_profile(
    solution: ExtractedSolution,
    ballots: Sequence[Sequence[int]],
    weights: ArrayLike,
    candidates: Sequence[str],
) -> None:
    """Check that a solution can be interpreted with the supplied election profile.

    Args:
        solution (ExtractedSolution): Extracted centers, assignments, and model name.
        ballots (Sequence[Sequence[int]]): Indexed rankings in model ballot order.
        weights (ArrayLike): Ballot frequencies in the same order.
        candidates (Sequence[str]): Labels in model candidate order.

    Returns:
        None: Valid input is left unchanged. Matching dimensions do not establish common provenance.

    Raises:
        KeyError: If required solution fields are missing.
        ValueError: If the profile, indices, or dimensions are invalid.
    """
    validate_profile(ballots, weights, len(candidates))
    centers, assignments = solution["centers"], solution["assignments"]

    if len(ballots) != len(assignments):
        raise ValueError("Solution ballot count does not match the election profile")

    if any(type(r) is not int or not 0 <= r < len(centers) for r in assignments):
        raise ValueError("Invalid cluster labels")

    dimension = len(candidates)

    if solution["model"].endswith("head_to_head"):
        dimension = dimension * (dimension - 1) // 2

    if solution["center_kind"] == "ballot_index":
        if any(type(j) is not int or not 0 <= j < len(ballots) for j in solution["centers"]):
            raise ValueError("Invalid center ballot indices")
    elif any(len(center) != dimension for center in solution["centers"]):
        raise ValueError("Center dimensions do not match the candidate count")


def build_ballot_clusters(
    ballots: Sequence[Sequence[int]],
    weights: Sequence[float],
    coordinates: Sequence[Sequence[float]],
    assignments: Sequence[int],
    n_clusters: int,
) -> PairedBallotClusters:
    """Pair embedded and CVR rankings with frequencies in saved cluster and ballot order.

    Input rankings use zero-based candidate indices; Scottish CVR rankings use one-based IDs.
    Keep every center slot and every distinct input ranking, even if embeddings coincide.

    Args:
        ballots (Sequence[Sequence[int]]): Distinct zero-based rankings in model ballot order.
        weights (Sequence[float]): Positive integer-valued frequencies corresponding to ballots.
        coordinates (Sequence[Sequence[float]]): Embedded ballots in the same order.
        assignments (Sequence[int]): Zero-based cluster label for each ballot.
        n_clusters (int): Number of center slots, including empty clusters.

    Returns:
        PairedBallotClusters: Coordinate and CVR memberships with matching order and frequencies.

    Raises:
        ValueError: If input lengths differ, labels are out of range, or frequencies are invalid.
    """
    if not len(ballots) == len(weights) == len(coordinates) == len(assignments):
        raise ValueError("Ballots, weights, coordinates, and assignments must have equal lengths")

    embedded: BallotMemberships = [[] for _ in range(n_clusters)]
    cvr: BallotMemberships = [[] for _ in range(n_clusters)]

    for ballot, weight, point, r in zip(ballots, weights, coordinates, assignments):
        if type(r) is not int or not 0 <= r < n_clusters:
            raise ValueError("Invalid cluster label")

        if not math.isfinite(weight) or weight <= 0 or int(weight) != weight:
            raise ValueError("Ballot frequencies must be positive integers")

        embedded[r].append([list(point), int(weight)])
        cvr[r].append([[int(candidate) + 1 for candidate in ballot], int(weight)])

    return {
        "ballot_clusters_in_coordinates": embedded,
        "ballot_clusters_from_cvr": cvr,
    }


def solutions_to_csv(solutions: Iterable[ExtractedSolution], path: str | Path) -> int:
    """Stream extracted solutions into a CSV with one row per solution.

    Centers and assignments use JSON cells, preserving nested arrays and cluster labels. The source
    path identifies each run. No solver status is inferred from a SOL file. An existing destination
    is never overwritten. A failed iteration or write may leave a partial CSV.

    Args:
        solutions (Iterable[ExtractedSolution]): Extracted solutions supplied as a collection or
            generator.
        path (str | Path): New destination CSV file; its parent directory must exist.

    Returns:
        int: Number of solution rows written, excluding the header.

    Raises:
        OSError: If the destination exists or cannot be written.
        KeyError: If an extracted solution is missing a required field.
        TypeError: If centers or assignments cannot be serialized as JSON.
        ValueError: If structured fields contain nonfinite numbers.
    """
    fields = [
        "source",
        "model",
        "objective",
        "n_ballots",
        "n_clusters",
        "center_kind",
        "centers",
        "assignments",
    ]
    count = 0

    with Path(path).open("x", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()

        for solution in solutions:
            row: dict[str, object] = {
                "source": solution["source"],
                "model": solution["model"],
                "objective": solution["objective"],
                "center_kind": solution["center_kind"],
            }
            row.update(n_ballots=len(solution["assignments"]), n_clusters=len(solution["centers"]))

            row["centers"] = json.dumps(solution["centers"], allow_nan=False, separators=(",", ":"))
            row["assignments"] = json.dumps(
                solution["assignments"], allow_nan=False, separators=(",", ":")
            )

            writer.writerow(row)
            count += 1

    return count
