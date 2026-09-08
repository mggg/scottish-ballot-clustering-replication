"""Check archive round trips, validation, streaming, and atomic publication."""

import json
from collections.abc import Iterator
from pathlib import Path
from zipfile import ZipFile

import pytest
from click.testing import CliRunner

from analysis_scripts.archive_solutions import main
from scottish_ballot_clustering.saved_solutions import (
    SavedSolution,
    iter_archived_solutions,
    iter_saved_solutions,
    load_saved_solutions,
    save_solution,
    save_solution_archive,
)


def sample_solution() -> SavedSolution:
    """Return a minimal valid solution with paired clusters and a Unicode candidate name."""
    return {
        "election": "town",
        "candidates": ["Àlice"],
        "embedding": "borda_pessimistic",
        "optimization_model": "coordinate",
        "centers": [[0]],
        "ballot_clusters_in_coordinates": [[[[0], 7]]],
        "ballot_clusters_from_cvr": [[[[1], 7]]],
    }


def test_pack_cli_preserves_layout_and_refuses_overwrite(tmp_path: Path) -> None:
    """Package new loose results, read them directly, and replace only with explicit overwrite."""
    source = tmp_path / "1_clusters"
    candidates = source / "1_candidates"
    candidates.mkdir(parents=True)
    original = sample_solution()
    save_solution(original, candidates / "town.json")
    destination = tmp_path / "1_clusters.zip"
    args = [str(source), str(destination)]

    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    assert list(iter_archived_solutions(destination)) == [
        ("1_clusters/1_candidates/town.json", original)
    ]
    assert load_saved_solutions(destination) == [original]
    assert load_saved_solutions(candidates / "town.json") == [original]
    before = destination.read_bytes()

    assert CliRunner().invoke(main, args).exit_code != 0
    assert destination.read_bytes() == before

    updated: SavedSolution = {**original, "candidates": ["Bob"]}
    (candidates / "town.json").write_text(json.dumps(updated))
    assert CliRunner().invoke(main, [*args, "--overwrite"]).exit_code == 0
    assert load_saved_solutions(destination) == [updated]


def test_archive_reader_streams_and_validates_each_solution(tmp_path: Path) -> None:
    """Yield a valid first member before rejecting repeated JSON fields in the next member."""
    path = tmp_path / "solutions.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("first.json", json.dumps(sample_solution()))
        archive.writestr("second.json", '{"election": "town", "election": "other"}')

    solutions = iter_saved_solutions(path)
    assert next(solutions) == sample_solution()
    with pytest.raises(ValueError, match="Repeated JSON field"):
        next(solutions)


@pytest.mark.parametrize("name", ["../town.json", "/town.json", "town.txt", "C:/town.json"])
def test_archive_reader_and_writer_reject_invalid_names(tmp_path: Path, name: str) -> None:
    """Reject names that escape the result tree or cannot identify solution JSON files."""
    path = tmp_path / "solutions.zip"
    with pytest.raises(ValueError, match="member name"):
        save_solution_archive([(name, sample_solution())], path)
    assert not path.exists()

    with ZipFile(path, "w") as archive:
        archive.writestr(name, json.dumps(sample_solution()))
    with pytest.raises(ValueError, match="member name"):
        list(iter_saved_solutions(path))


@pytest.mark.parametrize("existing", [False, True])
def test_interrupted_archive_write_preserves_destination(tmp_path: Path, existing: bool) -> None:
    """Remove partial output and leave any previous archive byte-for-byte unchanged."""
    path = tmp_path / "solutions.zip"
    if existing:
        save_solution_archive([("original.json", sample_solution())], path)
    before = path.read_bytes() if existing else None

    def interrupted() -> Iterator[tuple[str, SavedSolution]]:
        """Fail after writing one member to the temporary archive."""
        yield "new.json", sample_solution()
        raise ValueError("Interrupted reconstruction")

    with pytest.raises(ValueError, match="Interrupted reconstruction"):
        save_solution_archive(interrupted(), path, overwrite=existing)

    assert (path.read_bytes() if path.exists() else None) == before
    assert list(tmp_path.iterdir()) == ([path] if existing else [])


def test_duplicate_archive_members_are_rejected(tmp_path: Path) -> None:
    """Reject repeated filenames rather than silently losing a solution."""
    path = tmp_path / "solutions.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("town.json", json.dumps(sample_solution()))
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("town.json", json.dumps(sample_solution()))
    with pytest.raises(ValueError, match="repeated solution member"):
        load_saved_solutions(path)
