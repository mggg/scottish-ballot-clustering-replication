"""Export integer-program SOL files beneath a result directory to one CSV."""

from pathlib import Path

import click

from scottish_ballot_clustering.extract_results import extract_solution, solutions_to_csv


@click.command(
    help="Recursively extract SOL files into a new CSV, one row per solution.\n\n"
    "RESULTS_DIR is searched recursively for integer-program .sol files.\n\n"
    "OUTPUT is a new CSV file, whose parent directory must exist. Existing files are never "
    "overwritten. An empty search writes only the CSV header."
)
@click.argument("results_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
def main(results_dir: Path, output: Path) -> None:
    """Stream saved IP solutions into a CSV without overwriting existing output.

    Args:
        results_dir (Path): Directory searched recursively for SOL files.
        output (Path): New CSV destination with an existing parent directory.

    Returns:
        None: The CSV is written and the number of exported solutions should be printed.
        An empty search writes a header-only CSV.

    Raises:
        click.ClickException: If a SOL file is malformed or file access fails. A failure during
            export may leave a partial CSV.
    """
    try:
        count = solutions_to_csv(
            (extract_solution(path) for path in results_dir.rglob("*.sol")), output
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Exported {count} solutions to {output}")


if __name__ == "__main__":
    main()
