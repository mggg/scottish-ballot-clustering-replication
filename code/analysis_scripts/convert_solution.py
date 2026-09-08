"""Convert one current SOL output to portable centers and paired ballot clusters."""

from pathlib import Path

import click

from scottish_ballot_clustering.saved_solutions import convert_sol_to_saved_solution, save_solution


@click.command(
    help="Convert a SOL and its original election CSV to a new saved-solution JSON.\n\n"
    "SOLUTION is a complete Gurobi SOL file produced by an integer-program model. "
    "ELECTION_CSV is the original Scottish election CSV, preserving candidate and ballot order.\n\n"
    "OUTPUT is a new JSON file containing centers and cluster memberships. Its parent directory "
    "must exist; existing files are never overwritten."
)
@click.argument("solution", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("election_csv", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
def main(solution: Path, election_csv: Path, output: Path) -> None:
    """Export centers and saved cluster memberships without optimizing or overwriting output."""
    try:
        save_solution(convert_sol_to_saved_solution(solution, election_csv), output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Saved solution: {output}")


if __name__ == "__main__":
    main()
