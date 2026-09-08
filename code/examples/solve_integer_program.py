"""Solve a small weighted election using each public integer-program builder."""

import numpy as np

from scottish_ballot_clustering.metrics import ballot_borda_vector, pairwise_manhattan
from scottish_ballot_clustering.models import (
    AllBallotModelName,
    CastBallotModelName,
    CoordinateModelName,
    build_all_ballot_model,
    build_cast_ballot_model,
    build_coordinate_model,
)


def main() -> None:
    """Build and solve three Borda models on the same synthetic profile.

    Candidate indices are 0, 1, and 2. Frequencies weight distinct partial rankings. Coordinate
    models receive embedded ballots; the cast-ballot model receives pairwise distances instead.
    Each context manager disposes of its model after inspection.

    Returns:
        None: Print each model's objective and selected assignment indicators when feasible.

    Raises:
        gurobipy.GurobiError: If licensing, model construction, or solving fails.
    """
    ballots = [(0, 1, 2), (1, 2), (2, 0), (0,)]
    weights = np.array([5, 3, 2, 1])
    coordinates = np.array([ballot_borda_vector(ballot=list(b), n_candidates=3) for b in ballots])

    for builder, name in (
        (build_cast_ballot_model, CastBallotModelName.BORDA),
        (build_coordinate_model, CoordinateModelName.BORDA),
        (build_all_ballot_model, AllBallotModelName.BORDA),
    ):
        inputs = {"model_name": name, "weight_vector": weights, "n_clusters": 2}

        if builder is build_cast_ballot_model:
            inputs.update(n_ballots=len(ballots), cost_matrix=pairwise_manhattan(coordinates))
            assignment_prefix = "cluster_assignment["
        else:
            inputs.update(
                ballots_as_coordinates_array=coordinates, value_vector=np.arange(3), n_candidates=3
            )
            assignment_prefix = "ballot_j_to_cluster_r_indicator["

        with builder(**inputs) as model:
            model.Params.OutputFlag = 0
            # Set solver parameters or add application-specific constraints before optimizing.
            model.optimize()

            if model.SolCount:
                print(f"{name}: objective={model.ObjVal}, status={model.Status}")
                print(
                    [
                        v.VarName
                        for v in model.getVars()
                        if v.VarName.startswith(assignment_prefix) and v.X > 0.5
                    ]
                )
            else:
                print(f"{name}: no feasible solution, status={model.Status}")


if __name__ == "__main__":
    main()
