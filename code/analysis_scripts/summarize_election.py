"""Print weighted election statistics and optional IP cluster statistics as JSON."""

import json
from pathlib import Path
from typing import NotRequired, TypedDict

import click

from scottish_ballot_clustering.extract_results import extract_solution, rebuild_clusters
from scottish_ballot_clustering.load_election import load_election
from scottish_ballot_clustering.summarize_profiles import (
    ClusterSummary,
    ElectionSummary,
    summarize_clusters,
    summarize_election,
)


class ElectionReport(TypedDict):
    """Describe the JSON report with optional cluster statistics.

    Attributes:
        election (ElectionSummary): Weighted statistics for the full election profile.
        clusters (NotRequired[list[ClusterSummary]]): Per-cluster statistics, present only when a
            companion solution was supplied.
    """

    election: ElectionSummary
    clusters: NotRequired[list[ClusterSummary]]


@click.command(
    help="Summarize an election CSV. Print JSON to standard output.\n\n"
    "INPUT_FILE is a Scottish election CSV containing ranked ballots and their frequencies. "
    "With --solution, use the original CSV that built the model so candidate and ballot order "
    "match the SOL file."
)
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--solution",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Also summarize this SOL's clusters using the election CSV that built its model.",
)
@click.option(
    "--top-n",
    type=click.IntRange(min=0),
    default=10,
    show_default=True,
    help="Maximum number of most frequent rankings to report per election or cluster; 0 lists none.",
)
def main(input_file: Path, solution: Path | None, top_n: int) -> None:
    """Print election statistics with optional reconstructed cluster statistics.

    Args:
        input_file (Path): Scottish election CSV, loaded in the same order used to build the model.
        solution (Path | None): SOL for this election, or None for election only.
        top_n (int): Nonnegative maximum number of common rankings per profile.

    Returns:
        None: Print a JSON object containing election and, when requested, clusters statistics.

    Raises:
        click.ClickException: If inputs cannot be read or the profile or solution is invalid.
        pandas.errors.DataError: If the election loader rejects the CSV's records.
    """
    try:
        ballots, weights, candidates = load_election(input_file)

        result: ElectionReport = {
            "election": summarize_election(
                ballots,
                weights,
                candidates,
                top_n=top_n,
            )
        }

        if solution is not None:
            clusters = rebuild_clusters(extract_solution(solution), ballots, weights, candidates)
            result["clusters"] = summarize_clusters(clusters, top_n=top_n)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
