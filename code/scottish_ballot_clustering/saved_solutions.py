"""Read and write portable centers and paired ballot clusters in explicit candidate order."""

import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import cast
from zipfile import ZIP_DEFLATED, ZipFile

from .extract_results import build_ballot_clusters, extract_solution, validate_solution_profile
from .load_election import load_election
from .metrics import ballot_borda_vector, ballot_hh_vector
from .solution_types import CenterMetadata, SavedSolution


def validate_saved_solution(data: object) -> SavedSolution:
    """Validate center metadata and paired ballot memberships without certifying optimality.

    Both membership fields are required. Duplicate centers and empty cluster slots
    are preserved. Valid centers need not encode consistent all-ballot rankings or cast ballots.

    Args:
        data (object): Decoded JSON object with center metadata and both membership representations.

    Returns:
        SavedSolution: The original object after validation; no values or ordering are changed.

    Raises:
        ValueError: If fields, centers, memberships, or corresponding embeddings are invalid.
    """
    center_fields = {"election", "candidates", "embedding", "optimization_model", "centers"}
    cluster_fields = {"ballot_clusters_in_coordinates", "ballot_clusters_from_cvr"}
    if not isinstance(data, dict) or set(data) != center_fields | cluster_fields:
        raise ValueError("A saved solution requires five center fields and both cluster fields")

    metadata = _validate_center_metadata(data)
    _validate_paired_memberships(data, metadata)

    return cast(SavedSolution, data)


def _validate_center_metadata(data: dict[str, object]) -> CenterMetadata:
    """Check election labels, model variants, and center geometry before interpreting memberships.

    Args:
        data (dict[str, object]): JSON object whose required field names have been checked.

    Returns:
        CenterMetadata: Original metadata with unique candidate labels and valid center coordinates.

    Raises:
        ValueError: If labels, variants, center dimensions, or coordinate values are invalid.
    """
    if not isinstance(data["election"], str) or not data["election"].strip():
        raise ValueError("Election must be a nonempty string")

    candidates = data["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Candidates must be a nonempty list")
    if any(not isinstance(name, str) or not name.strip() for name in candidates):
        raise ValueError("Candidate names must be nonempty strings")
    if len(set(candidates)) != len(candidates):
        raise ValueError("Candidate names must be unique")

    if data["embedding"] not in ("borda_pessimistic", "head_to_head"):
        raise ValueError("Unsupported embedding")
    if data["optimization_model"] not in ("coordinate", "all_ballot", "cast_ballot"):
        raise ValueError("Unsupported optimization model")

    n_candidates = len(candidates)
    head_to_head = data["embedding"] == "head_to_head"
    dimension = n_candidates * (n_candidates - 1) // 2 if head_to_head else n_candidates
    allowed = range(-1, 2) if head_to_head else range(n_candidates)
    centers = data["centers"]
    if not isinstance(centers, list) or not centers:
        raise ValueError("Centers must be nonempty as a collection")

    for center in centers:
        if not isinstance(center, list) or len(center) != dimension:
            raise ValueError("Center dimensions do not match the candidate count and embedding")
        if any(type(value) not in (int, float) or value not in allowed for value in center):
            raise ValueError("Center coordinates must be integer values in the embedding's range")

    return cast(CenterMetadata, data)


def _validate_paired_memberships(data: dict[str, object], metadata: CenterMetadata) -> None:
    """Check corresponding cluster entries and require each CVR ranking to occur exactly once.

    Args:
        data (dict[str, object]): JSON object containing both membership fields.
        metadata (CenterMetadata): Validated centers and candidate indexing for these memberships.

    Returns:
        None: Leave valid membership arrays unchanged.

    Raises:
        ValueError: If cluster structure, paired entries, or ranking uniqueness are invalid.
    """
    embedded = data["ballot_clusters_in_coordinates"]
    cvr = data["ballot_clusters_from_cvr"]
    n_clusters = len(metadata["centers"])
    if (
        not isinstance(embedded, list)
        or not isinstance(cvr, list)
        or len(embedded) != n_clusters
        or len(cvr) != n_clusters
    ):
        raise ValueError("Both cluster lists must have one entry per center")

    seen: set[tuple[int, ...]] = set()
    for points, rankings in zip(embedded, cvr):
        if (
            not isinstance(points, list)
            or not isinstance(rankings, list)
            or len(points) != len(rankings)
        ):
            raise ValueError(
                "Cluster representations must contain matching lists of ballot entries"
            )

        for point_entry, cvr_entry in zip(points, rankings):
            ranking = _validate_membership_pair(point_entry, cvr_entry, metadata)
            if ranking in seen:
                raise ValueError("Each distinct CVR ranking must appear exactly once")

            seen.add(ranking)


def _validate_membership_pair(
    point_entry: object, cvr_entry: object, metadata: CenterMetadata
) -> tuple[int, ...]:
    """Validate a weighted CVR and its coordinate entry, returning its one-based ranking key.

    Args:
        point_entry (object): JSON coordinate-vector and frequency pair.
        cvr_entry (object): Corresponding one-based CVR ranking and frequency pair.
        metadata (CenterMetadata): Validated candidate indexing and embedding convention.

    Returns:
        tuple[int, ...]: CVR ranking for membership-uniqueness checks.

    Raises:
        ValueError: If entry shapes, weights, ranking IDs, or corresponding coordinates disagree.
    """
    if (
        not isinstance(point_entry, list)
        or not isinstance(cvr_entry, list)
        or len(point_entry) != 2
        or len(cvr_entry) != 2
    ):
        raise ValueError("A ballot entry must be [ranking, weight]")

    point, weight = point_entry
    ranking, cvr_weight = cvr_entry
    if type(weight) is not int or weight <= 0 or type(cvr_weight) is not int:
        raise ValueError("Ballot weights must be positive integers")
    if weight != cvr_weight:
        raise ValueError("Corresponding ballot weights disagree")

    n_candidates = len(metadata["candidates"])
    if (
        not isinstance(ranking, list)
        or any(type(i) is not int or not 1 <= i <= n_candidates for i in ranking)
        or len(set(ranking)) != len(ranking)
    ):
        raise ValueError("CVR rankings must contain distinct one-based candidate IDs")

    embed = ballot_hh_vector if metadata["embedding"] == "head_to_head" else ballot_borda_vector
    expected = embed(ballot=[i - 1 for i in ranking], n_candidates=n_candidates).tolist()
    if not isinstance(point, list) or any(type(value) not in (int, float) for value in point):
        raise ValueError("Embedded ballots must be coordinate lists")
    if point != expected:
        raise ValueError("Ballot coordinates do not match the corresponding CVR ranking")

    return tuple(ranking)


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject repeated JSON fields rather than silently replacing election metadata."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Repeated JSON field: {key}")

        result[key] = value

    return result


def _read_json(path: str | Path) -> object:
    """Decode JSON while rejecting repeated object fields."""
    with Path(path).open(encoding="utf-8") as source:
        return json.load(source, object_pairs_hook=_unique_fields)


def load_saved_solution(path: str | Path) -> SavedSolution:
    """Read one JSON object, validating its metadata, centers, and both ballot cluster fields."""
    return validate_saved_solution(_read_json(path))


def load_saved_solutions(path: str | Path) -> list[SavedSolution]:
    """Load a JSON object, JSON array, or solution ZIP into memory.

    Use iter_saved_solutions for large ZIP collections to retain only one solution at a time.
    """
    return list(iter_saved_solutions(path))


def iter_saved_solutions(path: str | Path) -> Iterator[SavedSolution]:
    """Read validated solutions from JSON or stream them from a ZIP without extracting files.

    Args:
        path (str | Path): JSON object, JSON array, or ZIP containing individual JSON objects.

    Yields:
        SavedSolution: Solutions in JSON array order or ZIP member order. JSON arrays are loaded
        in full; ZIPs retain one decoded solution at a time.

    Raises:
        OSError: If the source cannot be read.
        ValueError: If JSON, solution fields, or archive member names are invalid.
        zipfile.BadZipFile: If the ZIP structure or a member's checksum is invalid.
    """
    if Path(path).suffix.lower() == ".zip":
        for _, solution in iter_archived_solutions(path):
            yield solution
        return

    data = _read_json(path)
    solutions = data if isinstance(data, list) else [data]
    for solution in solutions:
        yield validate_saved_solution(solution)


def _validate_member_name(name: str, seen: set[str]) -> None:
    """Require unique relative JSON paths that retain their meaning when extracted."""
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or any(part in ("", ".", "..") for part in name.split("/"))
        or any(character in name for character in ("\\", ":", "\x00"))
        or path.suffix != ".json"
        or name in seen
    ):
        raise ValueError(f"Invalid or repeated solution member name: {name!r}")


def iter_archived_solutions(path: str | Path) -> Iterator[tuple[str, SavedSolution]]:
    """Stream named JSON solutions from a solution archive, preserving member order.

    Args:
        path (str | Path): ZIP of individual solution objects with unique relative JSON paths.
            Directory entries are skipped; other non-JSON members are rejected.

    Yields:
        tuple[str, SavedSolution]: Member filename and validated solution. No files are extracted.

    Raises:
        OSError: If the source cannot be read.
        ValueError: If member names, JSON, or solution fields are invalid.
        zipfile.BadZipFile: If the ZIP structure or a member's checksum is invalid.
    """
    seen: set[str] = set()
    with ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue

            _validate_member_name(member.filename, seen)
            seen.add(member.filename)
            with archive.open(member) as source:
                data = json.load(source, object_pairs_hook=_unique_fields)

            yield member.filename, validate_saved_solution(data)


def save_solution_archive(
    solutions: Iterable[tuple[str, SavedSolution]], path: str | Path, *, overwrite: bool = False
) -> None:
    """Validate and write named solutions to a ZIP, publishing only the completed archive.

    Args:
        solutions (Iterable[tuple[str, SavedSolution]]): Unique relative JSON paths and solutions in
            the desired archive order. Each solution is serialized separately with ZIP DEFLATE.
        path (str | Path): Destination with an existing parent directory. Publishing without
            overwrite requires a filesystem supporting hard links, such as NTFS on Windows.
        overwrite (bool): Replace an existing archive atomically, copying its ordinary Unix
            permission bits or Windows read-only flag. Ownership, access control lists, and other
            file metadata are not copied.

    Returns:
        None: Publish a complete archive. A failure leaves an existing destination intact.

    Raises:
        FileExistsError: If the destination exists and overwrite is false.
        OSError: If writing or publishing fails, including unsupported hard links. On Windows,
            read-only destinations or open handles that disallow deletion can prevent replacement.
        ValueError: If member names, solution fields, or numeric values are invalid.
    """
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(path)

    with TemporaryDirectory(prefix=f".{path.name}-", dir=path.parent) as temporary:
        staged = Path(temporary) / path.name
        seen: set[str] = set()
        with ZipFile(staged, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for name, solution in solutions:
                _validate_member_name(name, seen)
                seen.add(name)
                validated = validate_saved_solution(solution)
                contents = json.dumps(validated, indent=2, ensure_ascii=False, allow_nan=False)
                archive.writestr(name, contents + "\n")

        if overwrite:
            if path.exists():
                staged.chmod(path.stat().st_mode & 0o777)
            staged.replace(path)
        else:
            os.link(staged, path)


def save_solution(solution: SavedSolution, path: str | Path) -> None:
    """Validate and write one portable solution; never overwrite an existing file."""
    validated = validate_saved_solution(solution)
    with Path(path).open("x", encoding="utf-8") as destination:
        json.dump(validated, destination, indent=2, ensure_ascii=False, allow_nan=False)
        destination.write("\n")


def convert_sol_to_saved_solution(path: str | Path, election_csv: str | Path) -> SavedSolution:
    """Convert this package's SOL to portable centers and clusters using its original election CSV.

    The CSV must have the candidate and ballot ordering used to build the model. The SOL header
    supplies the embedding and model, and the CSV stem supplies the election identifier.

    Args:
        path (str | Path): Complete SOL exported by this package.
        election_csv (str | Path): Original election CSV with matching candidate and ballot order.

    Returns:
        SavedSolution: Validated centers and both membership representations in saved cluster order.

    Raises:
        OSError: If the SOL or election CSV cannot be read.
        ValueError: If solution structure, profile dimensions, or published fields are invalid.
        KeyError: If the election references an undeclared candidate.
    """
    extracted = extract_solution(path)
    ballots, weights, candidates = load_election(election_csv)
    validate_solution_profile(extracted, ballots, weights, candidates)
    embedding = (
        "head_to_head" if extracted["model"].endswith("head_to_head") else "borda_pessimistic"
    )
    model = extracted["model"].removesuffix("_" + embedding)
    embed = ballot_hh_vector if embedding == "head_to_head" else ballot_borda_vector
    if extracted["center_kind"] == "ballot_index":
        centers = [
            embed(ballot=ballots[index], n_candidates=len(candidates)).tolist()
            for index in extracted["centers"]
        ]
    else:
        centers = extracted["centers"]

    coordinates = [
        embed(ballot=b, n_candidates=len(candidates)).astype(int).tolist() for b in ballots
    ]
    return validate_saved_solution(
        {
            "election": Path(election_csv).stem,
            "candidates": candidates,
            "embedding": embedding,
            "optimization_model": model,
            "centers": centers,
            **build_ballot_clusters(
                ballots, weights.tolist(), coordinates, extracted["assignments"], len(centers)
            ),
        }
    )
