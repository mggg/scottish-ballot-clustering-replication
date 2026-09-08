"""Check warm-start feasibility, unrestricted optimization, and SOL integration."""

import json
import tempfile
import unittest
from itertools import permutations, product
from pathlib import Path
from unittest.mock import patch

import gurobipy as gp
import numpy as np
from click.testing import CliRunner

from scottish_ballot_clustering.extract_results import extract_solution
from scottish_ballot_clustering.load_election import load_election
from scottish_ballot_clustering.metrics import ballot_borda_vector, ballot_hh_vector
from scottish_ballot_clustering.pam import pam
from scottish_ballot_clustering.run_clustering import build_model, main
from scottish_ballot_clustering.saved_solutions import convert_sol_to_saved_solution, save_solution
from scottish_ballot_clustering.warm_start import (
    apply_pam_warm_start,
    apply_warm_start,
    load_pam_medoids,
)


class WarmStartTests(unittest.TestCase):
    """Exercise both center families without changing the feasible region."""

    def test_pam_starts_complete_at_the_expected_cost_in_every_model(self) -> None:
        """Keep medoid ownership under identical embeddings and reorder unequal clusters together."""
        ballots = [(0, 1), (0, 1, 2), (2,), (1,), (1, 0)]
        weights = np.array([4, 2, 3, 1, 5])
        for metric, family, k in product(
            ("borda", "head_to_head"), ("cast_ballot", "all_ballot", "coordinate"), (1, 2, 5)
        ):
            with self.subTest(metric=metric, family=family, k=k):
                embed = ballot_borda_vector if metric == "borda" else ballot_hh_vector
                coordinates = np.array([embed(ballot=b, n_candidates=3) for b in ballots])
                source = pam(coordinates, weights, k)
                medoids = source["medoid_indices"]
                distances = np.abs(coordinates[:, None, :] - coordinates[medoids]).sum(axis=2)
                labels = distances.argmin(axis=1)
                labels[medoids] = np.arange(k)
                expected_cost = source["objective"]
                if family == "coordinate":
                    expected_cost = sum(
                        min(
                            weights[labels == r] @ np.abs(coordinates[labels == r, i] - value)
                            for value in set(coordinates[:, i])
                        )
                        for r in range(k)
                        for i in range(coordinates.shape[1])
                    )
                    if k == 1:
                        self.assertLess(expected_cost, source["objective"])
                elif family == "all_ballot":
                    possible_centers = [
                        embed(ballot=ranking, n_candidates=3)
                        for length in range(4)
                        for ranking in permutations(range(3), length)
                    ]
                    expected_cost = sum(
                        min(
                            weights[labels == r]
                            @ np.abs(coordinates[labels == r] - center).sum(axis=1)
                            for center in possible_centers
                        )
                        for r in range(k)
                    )
                with build_model(ballots, weights, 3, metric, family, k) as model:
                    model.Params.OutputFlag = 0
                    model.Params.Threads = 1
                    model.update()
                    bounds = [(v.LB, v.UB) for v in model.getVars()]
                    apply_pam_warm_start(
                        model, source["medoid_indices"][::-1], coordinates, weights, k
                    )
                    model.update()
                    self.assertEqual(bounds, [(v.LB, v.UB) for v in model.getVars()])
                    starts = {v.VarName: v.Start for v in model.getVars()}
                    with model.copy() as fixed:
                        for var in fixed.getVars():
                            if starts[var.VarName] != gp.GRB.UNDEFINED:
                                var.LB = var.UB = starts[var.VarName]
                        fixed.optimize()
                        self.assertEqual(fixed.Status, gp.GRB.OPTIMAL)
                        self.assertAlmostEqual(fixed.ObjVal, expected_cost)
                    with model.copy() as cold:
                        cold.optimize()
                        model.optimize()
                        self.assertAlmostEqual(model.ObjVal, cold.ObjVal)

    def test_pam_json_validation(self) -> None:
        """Validate reusable PAM stdout and reject corrupt medoids, memberships, and cost."""
        election = (
            Path(__file__).resolve().parents[2]
            / "data/scot-elex/03_cands/eilean_siar_2022_ward3.csv"
        )
        ballots, weights, candidates = load_election(election)
        coordinates = np.array(
            [ballot_borda_vector(ballot=b, n_candidates=len(candidates)) for b in ballots]
        )
        runner = CliRunner()
        common = ["--file", str(election), "--run-type", "borda", "-k", "2"]
        result = runner.invoke(main, ["pam", *common])
        self.assertEqual(result.exit_code, 0, result.output)
        source = json.loads(result.output)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "pam.json"
            path.write_text(result.output)
            self.assertEqual(
                load_pam_medoids(path, coordinates, weights, 2), source["medoid_indices"]
            )
            for change in (
                {"medoid_indices": [0, 0]},
                {"medoid_indices": [0, len(ballots)]},
                {"medoid_indices": [False, 1]},
                {"medoid_indices": [0.5, 1]},
                {"objective": source["objective"] + 1},
                {"assignment_weights": [[1, 0]]},
            ):
                path.write_text(json.dumps(source | change))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    load_pam_medoids(path, coordinates, weights, 2)

    def test_pam_flag_runs_matching_profile_and_preserves_output_on_failure(self) -> None:
        """Run PAM once per IP without a file and reject incompatible starts before overwriting."""
        election = (
            Path(__file__).resolve().parents[2]
            / "data/scot-elex/03_cands/eilean_siar_2022_ward3.csv"
        )
        ballots, weights, candidates = load_election(election)
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as directory:
            for family, metric in product(
                ("cast-ballot", "all-ballot", "coordinate"), ("borda", "head_to_head")
            ):
                output = Path(directory) / family / metric
                args = [
                    family,
                    "--file",
                    str(election),
                    "--run-type",
                    metric,
                    "-k",
                    "2",
                    "--pam-start",
                    "--output-dir",
                    str(output),
                ]
                with patch("scottish_ballot_clustering.run_clustering.pam", wraps=pam) as prepare:
                    result = runner.invoke(main, args)

                self.assertEqual(result.exit_code, 0, result.output)
                prepare.assert_called_once()
                call = prepare.call_args
                assert call is not None
                embed = ballot_borda_vector if metric == "borda" else ballot_hh_vector
                expected = np.array(
                    [embed(ballot=b, n_candidates=len(candidates)) for b in ballots]
                )
                np.testing.assert_array_equal(call.args[0], expected)
                np.testing.assert_array_equal(call.args[1], weights)
                self.assertEqual(call.args[2], 2)

                saved = next(output.rglob("*.sol"))
                previous = saved.read_bytes()
                with patch(
                    "scottish_ballot_clustering.run_clustering.pam",
                    side_effect=ValueError("PAM failed"),
                ):
                    result = runner.invoke(main, [*args, "--overwrite"])
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("PAM failed", result.output)
                self.assertEqual(saved.read_bytes(), previous)

                result = runner.invoke(main, [*args, "--warm-start", str(saved), "--overwrite"])
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("only one starting solution", result.output)
                self.assertEqual(saved.read_bytes(), previous)

    def test_starts_are_feasible_and_leave_the_search_free(self) -> None:
        """Complete every supplied start exactly, including singleton and empty-cluster cases."""
        ballots = [(0, 1, 2), (2, 1, 0), (1,), (0,)]
        weights = np.array([4, 2, 3, 1])
        partitions = [(1, [0, 0, 0, 0]), (2, [0, 0, 0, 1]), (3, [0, 0, 1, 2]), (2, [1] * 4)]

        for family, metric, (k, labels) in product(
            ("cast_ballot", "coordinate", "all_ballot"), ("borda", "head_to_head"), partitions
        ):
            with self.subTest(family=family, metric=metric, k=k, labels=labels):
                embedding = ballot_borda_vector if metric == "borda" else ballot_hh_vector
                coordinates = np.array([embedding(ballot=b, n_candidates=3) for b in ballots])
                with build_model(ballots, weights, 3, metric, family, k) as model:
                    model.Params.OutputFlag = 0
                    model.Params.Threads = 1
                    model.update()
                    bounds = [(v.LB, v.UB) for v in model.getVars()]
                    if family == "cast_ballot" and len(set(labels)) != k:
                        with self.assertRaisesRegex(ValueError, "nonempty clusters"):
                            apply_warm_start(model, labels, coordinates, weights, k)
                        self.assertTrue(all(v.Start == gp.GRB.UNDEFINED for v in model.getVars()))
                        continue

                    apply_warm_start(model, labels, coordinates, weights, k)
                    model.update()
                    self.assertEqual(bounds, [(v.LB, v.UB) for v in model.getVars()])
                    starts = {
                        v.VarName: v.Start for v in model.getVars() if v.Start != gp.GRB.UNDEFINED
                    }
                    expected_variables = 4 * 4 + 4 if family == "cast_ballot" else 4 * k + 3 * k * 3
                    self.assertEqual(len(starts), expected_variables)

                    with model.copy() as fixed:
                        for variable in fixed.getVars():
                            if variable.VarName in starts:
                                variable.LB = variable.UB = starts[variable.VarName]
                        fixed.optimize()
                        self.assertGreater(fixed.SolCount, 0)
                        start_objective = fixed.ObjVal

                    if family == "cast_ballot":
                        expected_cost = sum(
                            min(
                                sum(
                                    weights[j] * np.abs(coordinates[i] - coordinates[j]).sum()
                                    for j in range(len(ballots))
                                    if labels[j] == cluster
                                )
                                for i in range(len(ballots))
                                if labels[i] == cluster
                            )
                            for cluster in range(k)
                        )
                        self.assertAlmostEqual(start_objective, expected_cost)

                    with model.copy() as cold:
                        cold.optimize()
                        model.optimize()
                        self.assertAlmostEqual(model.ObjVal, cold.ObjVal)

                    if labels == [1] * 4:
                        self.assertLess(model.ObjVal, start_objective)

    def test_cli_loads_current_sol_and_rejects_mismatches(self) -> None:
        """Use SOL and JSON starts in coordinate and all-ballot models and reject mismatches."""
        election = (
            Path(__file__).resolve().parents[2]
            / "data/scot-elex/03_cands/eilean_siar_2022_ward3.csv"
        )
        ballots, weights, candidates = load_election(election)
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cast.sol"
            with build_model(ballots, weights, len(candidates), "borda", "cast_ballot", 3) as cast:
                cast.Params.OutputFlag = 0
                cast.optimize()
                cast.write(str(source))
            source_bytes = source.read_bytes()
            saved_json = root / "cast.json"
            save_solution(convert_sol_to_saved_solution(source, election), saved_json)

            for family, starting_path in product(
                ("coordinate", "all-ballot"), (source, saved_json)
            ):
                args = [
                    family,
                    "--file",
                    str(election),
                    "--run-type",
                    "borda",
                    "-k",
                    "3",
                    "--warm-start",
                    str(starting_path),
                    "--output-dir",
                    str(root / family / starting_path.suffix),
                ]
                result = runner.invoke(main, args)
                self.assertEqual(result.exit_code, 0, result.output)
                saved = next((root / family / starting_path.suffix).rglob("*.sol"))
                self.assertEqual(len(extract_solution(saved)["centers"]), 3)
                previous = saved.read_bytes()

                result = runner.invoke(main, args + ["--run-type", "head_to_head", "--overwrite"])
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("same metric", result.output)
                result = runner.invoke(main, args + ["-k", "2"])
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("cluster count", result.output)
                self.assertEqual(saved.read_bytes(), previous)

            self.assertEqual(source.read_bytes(), source_bytes)

    def test_invalid_start_and_infeasible_center_solve(self) -> None:
        """Reject malformed labels and failed auxiliary solves without assigning a partial start."""
        ballots, weights = [(0,), (1,)], np.array([1, 1])
        coordinates = np.array([[1, 0], [0, 1]])
        with build_model(ballots, weights, 2, "borda", "all_ballot", 2) as model:
            model.Params.OutputFlag = 0
            for labels in ([0], [0, 2], [0.5, 1]):
                with self.assertRaises(ValueError):
                    apply_warm_start(model, labels, coordinates, weights, 2)

            model.addConstr(gp.LinExpr(0) == 1)
            with self.assertRaisesRegex(ValueError, "No feasible warm-start centers"):
                apply_warm_start(model, [0, 1], coordinates, weights, 2)
            model.update()
            self.assertTrue(all(v.Start == gp.GRB.UNDEFINED for v in model.getVars()))


if __name__ == "__main__":
    unittest.main()
