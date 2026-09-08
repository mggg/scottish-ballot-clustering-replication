"""Package individual solution JSON files into a validated ZIP archive."""

from pathlib import Path

import click

from scottish_ballot_clustering.saved_solutions import load_saved_solution, save_solution_archive


@click.command(
    help="Package individual solution JSON files into a validated ZIP archive.\n\n"
    "RESULTS_DIR is searched recursively for JSON files. Archive members retain their filenames "
    "and the enclosing directory name; source files are retained.\n\n"
    "OUTPUT is the destination .zip file, whose parent directory must exist. "
    "An existing archive requires --overwrite to replace."
)
@click.argument("results_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--overwrite", is_flag=True, help="Atomically replace an existing archive.")
def main(results_dir: Path, output: Path, overwrite: bool) -> None:
    """Archive results while retaining their filenames and enclosing directory name.

    Args:
        results_dir (Path): Directory searched recursively for individual solution JSON files.
        output (Path): ZIP destination with an existing parent directory.
        overwrite (bool): Allow replacing an existing archive after the new ZIP is complete.

    Returns:
        None: Write the archive and print its solution count. Source JSON files remain unchanged.

    Raises:
        click.ClickException: If there are no JSON files, an input is invalid, or writing fails.
    """
    results_dir = results_dir.resolve()
    paths = sorted(results_dir.rglob("*.json"))
    if not paths:
        raise click.ClickException(f"No solution JSON files found beneath {results_dir}")
    if output.suffix.lower() != ".zip":
        raise click.ClickException("Output must have a .zip extension")

    solutions = (
        (path.relative_to(results_dir.parent).as_posix(), load_saved_solution(path))
        for path in paths
    )
    try:
        save_solution_archive(solutions, output, overwrite=overwrite)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Archived {len(paths)} solutions to {output}")


if __name__ == "__main__":
    main()
