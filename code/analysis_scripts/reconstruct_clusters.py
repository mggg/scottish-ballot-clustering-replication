"""Reconstruct nearest-center ballot clusters in JSON files and solution ZIP archives."""

import json
import os
from collections.abc import Iterable, Iterator, Sequence
from itertools import groupby
from pathlib import Path
from tempfile import NamedTemporaryFile

import click
import numpy as np
from numpy.typing import NDArray

from scottish_ballot_clustering.extract_results import build_ballot_clusters
from scottish_ballot_clustering.load_election import load_election
from scottish_ballot_clustering.metrics import (
    ballot_borda_vector,
    ballot_hh_vector,
    pairwise_manhattan,
)
from scottish_ballot_clustering.saved_solutions import (
    SavedSolution,
    iter_archived_solutions,
    load_saved_solution,
    save_solution_archive,
    validate_saved_solution,
)


def reconstruct_solution(
    solution: SavedSolution,
    ballots: Sequence[Sequence[int]],
    weights: NDArray[np.int64],
    coordinates: NDArray[np.int64],
) -> SavedSolution:
    """Assign each ballot to its nearest stored center, choosing the first center on ties.

    Clusters are assigned by determining the Manhattan distance between each ballot's embedding and
    the stored centers.

    Args:
        solution (SavedSolution): Validated centers and metadata in the profile's candidate order.
        ballots (Sequence[Sequence[int]]): Distinct zero-based CVR rankings in profile order.
        weights (NDArray[np.int64]): Positive frequencies corresponding to ballots.
        coordinates (NDArray[np.int64]): Ballots embedded using the solution's convention.

    Returns:
        SavedSolution: Original metadata and centers with paired reconstructed ballot clusters.
        Duplicate centers and empty cluster slots remain in their original order.

    Raises:
        ValueError: If the profile dimensions or resulting paired representations are invalid.
    """
    centers = np.asarray(solution["centers"], dtype=np.int64)

    distances = pairwise_manhattan(coordinates, centers)
    assignments = distances.argmin(axis=1).tolist()

    clusters = build_ballot_clusters(
        ballots, weights.tolist(), coordinates.tolist(), assignments, len(centers)
    )

    return validate_saved_solution({**solution, **clusters})


def replace_json(path: Path, data: SavedSolution) -> None:
    """Atomically replace one individual solution JSON file.

    Args:
        path (Path): Existing destination. Copy its ordinary Unix permission bits or, on Windows,
            its read-only flag. Ownership, access control lists, and other file metadata are not
            copied.
        data (SavedSolution): Solution object to serialize.

    Returns:
        None: Replace the destination only after its complete JSON has been written.

    Raises:
        OSError: If writing or replacing the file fails; the previous destination remains intact
            if replacement has not occurred. On Windows, read-only destinations or open handles
            that disallow deletion can prevent replacement or temporary-file cleanup.
        ValueError: If serialization encounters a nonfinite numeric value.
    """
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            json.dump(data, output, indent=2, ensure_ascii=False, allow_nan=False)
            output.write("\n")

        os.chmod(temporary, path.stat().st_mode & 0o777)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def reconstruct_solutions(
    solutions: Iterable[tuple[str, SavedSolution]], elections: dict[str, Path]
) -> Iterator[tuple[str, SavedSolution]]:
    """Rebuild named solutions in order, retaining one election profile and embedding at a time.

    Args:
        solutions (Iterable[tuple[str, SavedSolution]]): Filenames paired with validated solutions.
        elections (dict[str, Path]): Original election CSVs indexed by their unique stems.

    Yields:
        tuple[str, SavedSolution]: Original filenames with reconstructed cluster memberships.

    Raises:
        ValueError: If an election is missing, a result is repeated, or candidate order differs.
        OSError: If an election CSV cannot be read.
    """
    seen = set()
    grouped = groupby(solutions, key=lambda entry: (entry[1]["election"], entry[1]["embedding"]))
    for (election, embedding), group in grouped:
        if election not in elections:
            raise ValueError(f"Missing election CSV: {election}")

        ballots, weights, candidates = load_election(elections[election])
        embed = ballot_hh_vector if embedding == "head_to_head" else ballot_borda_vector
        coordinates = np.asarray(
            [embed(ballot=b, n_candidates=len(candidates)) for b in ballots], dtype=np.int64
        )

        for name, solution in group:
            key = (election, embedding, solution["optimization_model"], len(solution["centers"]))
            if key in seen:
                raise ValueError(f"Repeated individual result: {key}")
            seen.add(key)

            if solution["candidates"] != candidates:
                raise ValueError(f"CSV candidate order does not match saved centers: {name}")

            yield name, reconstruct_solution(solution, ballots, weights, coordinates)


def reconstruct_collection(results_dir: Path, elections_dir: Path) -> None:
    """Reconstruct loose JSON results and ZIP members from their original election CSVs.

    Each JSON file or ZIP is replaced atomically. A failure leaves the current destination intact;
    earlier completed replacements remain. No solver is invoked and no master arrays are created.

    Args:
        results_dir (Path): Tree containing individual solution JSON files or solution ZIPs.
        elections_dir (Path): Tree of original election CSVs with unique stems.

    Returns:
        None: Replace the supplied results and print progress for each completed file or ZIP.

    Raises:
        ValueError: If a solution, archive member, or election metadata is invalid or inconsistent.
        OSError: If inputs cannot be read or outputs cannot be replaced.
        zipfile.BadZipFile: If an input ZIP is corrupt.
    """
    elections = {path.stem: path for path in elections_dir.rglob("*.csv")}
    paths = sorted(results_dir.rglob("*.json"))
    solutions = ((str(path), load_saved_solution(path)) for path in paths)
    for name, updated in reconstruct_solutions(solutions, elections):
        replace_json(Path(name), updated)
        click.echo(f"Updated {name}")

    for path in sorted(results_dir.rglob("*.zip")):
        updated_solutions = reconstruct_solutions(iter_archived_solutions(path), elections)
        save_solution_archive(updated_solutions, path, overwrite=True)
        click.echo(f"Updated {path}")


@click.command(
    help="Reconstruct nearest-center ballot clusters in JSON files and solution ZIP archives.\n\n"
    "RESULTS_DIR is searched recursively for individual solution JSON files and solution ZIPs. "
    "These files are replaced in place with reconstructed memberships.\n\n"
    "ELECTIONS_DIR is searched recursively for the original Scottish election CSVs, with unique "
    "filename stems and candidate order matching the saved centers.\n\n"
    "Assign ballots by Manhattan distance in the saved embedding, choosing the first stored "
    "center on ties. Each file or archive is replaced atomically; earlier replacements remain "
    "if a later input fails."
)
@click.argument("results_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("elections_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def main(results_dir: Path, elections_dir: Path) -> None:
    """Reconstruct and replace the supplied result collection from its election CSVs."""
    reconstruct_collection(results_dir, elections_dir)


if __name__ == "__main__":
    main()
