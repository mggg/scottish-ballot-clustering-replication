"""Run one clustering job with solver runtime settings supplied by the batch worker."""

import click

from scottish_ballot_clustering.run_clustering import build_model_command


def create_cli() -> click.Group:
    """Build fresh model commands with HPC runtime settings.

    Returns:
        click.Group: Independent command registry with a time limit for every model and a thread
        option for IP models only. Ordinary model commands are not modified.
    """
    group = click.Group(help="Run a clustering model with HPC runtime settings.")

    for family in ("cast_ballot", "all_ballot", "coordinate", "pam"):
        command = build_model_command(family)
        command.params.append(
            click.Option(
                ["--time-limit"],
                type=click.FloatRange(min=0, min_open=True),
                help="Seconds for IP optimization or PAM SWAP, excluding setup and output. "
                "No time limit if omitted.",
            )
        )

        if family != "pam":
            command.params.append(
                click.Option(
                    ["--threads"],
                    type=click.IntRange(min=1),
                    help="Gurobi thread limit. Use the solver's default if omitted.",
                )
            )

        group.add_command(command)

    return group


main = create_cli()


if __name__ == "__main__":
    main()
