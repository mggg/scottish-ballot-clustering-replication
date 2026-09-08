"""Write a tab-separated manifest: file, model family, metric, cluster count."""

import argparse
from itertools import product
from pathlib import Path


def _argument_parser() -> argparse.ArgumentParser:
    """Build a fresh argument parser for job-manifest selection.

    Returns:
        argparse.ArgumentParser: Parser for election, model, metric, and cluster-count filters.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/scot-elex"))
    parser.add_argument("--n-clusters", "-k", type=int, nargs="+", default=[2])
    parser.add_argument(
        "--n-candidates", type=int, nargs="+", help="Include only these candidate counts"
    )
    parser.add_argument(
        "--opt-type",
        nargs="+",
        choices=["cast_ballot", "all_ballot", "coordinate", "pam"],
        default=["cast_ballot", "all_ballot", "coordinate"],
    )
    parser.add_argument(
        "--run-type",
        nargs="+",
        choices=["borda", "head_to_head"],
        default=["borda", "head_to_head"],
    )

    return parser


def main() -> None:
    """Write selected election and model combinations to standard output.

    Arguments are read from the command line. Elections are sorted by path; each output row contains
    an absolute CSV path, model family, metric, and cluster count, separated by tabs. Candidate
    counts are taken from directory names such as ``07_cands``.

    Returns:
        None: Manifest rows are printed without a header.

    Raises:
        SystemExit: With status 2 if argument parsing fails, a cluster count is nonpositive, no
            elections match, or a selected path contains a tab or newline. Help exits with status 0.
            A late error may occur after some rows have been printed.
        ValueError: If candidate-count filtering encounters a nonnumeric directory prefix.
        OSError: If writing the manifest fails.
    """
    parser = _argument_parser()
    args = parser.parse_args()

    if any(k < 1 for k in args.n_clusters):
        parser.error("Cluster counts must be positive")

    files = sorted(args.data_dir.glob("*_cands/*.csv"))

    if args.n_candidates:
        files = [p for p in files if int(p.parent.name.split("_")[0]) in args.n_candidates]

    if not files:
        parser.error("No election CSV files matched")

    for path, family, metric, k in product(files, args.opt_type, args.run_type, args.n_clusters):
        name = str(path.resolve())

        if any(char in name for char in "\t\r\n"):
            parser.error("Election paths cannot contain tabs or newlines")

        print(f"{name}\t{family}\t{metric}\t{k}")


if __name__ == "__main__":
    main()
