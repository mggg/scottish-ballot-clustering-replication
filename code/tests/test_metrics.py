"""Check distance contracts, score selection, and weighted distance callbacks."""

import unittest
from functools import partial

import numpy as np

from scottish_ballot_clustering.metrics import (
    borda_distance,
    compute_cluster_cost,
    hh_distance,
    pairwise_manhattan,
)


class MetricTests(unittest.TestCase):
    """Verify the runtime contracts represented by metric annotations."""

    def test_pairwise_manhattan_with_one_or_two_arrays(self) -> None:
        """Preserve row ordering and raw L1 distances in square and rectangular matrices."""
        coordinates = np.array([[0, 1], [2, -1], [-1, 3]])
        centers = np.array([[1, 1], [0, -2]])

        np.testing.assert_array_equal(
            pairwise_manhattan(coordinates), [[0, 4, 3], [4, 0, 7], [3, 7, 0]]
        )
        distances = pairwise_manhattan(coordinates, centers)
        np.testing.assert_array_equal(distances, [[1, 3], [3, 3], [4, 6]])
        np.testing.assert_array_equal(pairwise_manhattan(centers, coordinates), distances.T)
        self.assertEqual(distances.dtype, np.dtype(np.float64))

    def test_pairwise_manhattan_empty_axes(self) -> None:
        """Keep empty row dimensions and zero distances for embeddings with no coordinates."""
        empty = np.empty((0, 2))
        points = np.zeros((3, 2))

        self.assertEqual(pairwise_manhattan(empty).shape, (0, 0))
        self.assertEqual(pairwise_manhattan(empty, points).shape, (0, 3))
        self.assertEqual(pairwise_manhattan(points, empty).shape, (3, 0))
        np.testing.assert_array_equal(
            pairwise_manhattan(np.empty((3, 0)), np.empty((2, 0))), np.zeros((3, 2))
        )

    def test_distance_values_and_score_selection(self) -> None:
        """Return native floats for both metrics and reject ambiguous Borda score selection."""
        distances = [
            hh_distance(ballot1=(0,), ballot2=[1], n_candidates=3),
            borda_distance(ballot1=(0,), ballot2=[1], n_candidates=3),
            borda_distance(ballot1=(0,), ballot2=[1], borda_vector=np.array([4, 2, 0])),
        ]
        self.assertEqual(distances, [4.0, 4.0, 8.0])
        self.assertTrue(all(type(distance) is float for distance in distances))

        with self.assertRaises(ValueError):
            borda_distance(ballot1=[], ballot2=[])

        with self.assertRaises(ValueError):
            borda_distance(ballot1=[], ballot2=[], n_candidates=3, borda_vector=np.array([2, 1, 0]))

        with self.assertRaises(ValueError):
            hh_distance(ballot1=[], ballot2=[], n_candidates=-1)

    def test_weighted_cluster_callback(self) -> None:
        """Check keyword calls to bound metrics and weighted and empty-cluster costs."""
        distance = partial(borda_distance, n_candidates=3)
        ballots = [(0,), (1,)]
        weights = np.array([2, 3])
        cost = compute_cluster_cost(
            cluster_set=frozenset({0, 1}),
            centroid_idx=0,
            ballot_list=ballots,
            weight_vector=weights,
            distance_function=distance,
        )
        self.assertEqual(cost, 12.0)
        self.assertIs(type(cost), float)

        empty_cost = compute_cluster_cost(
            cluster_set=frozenset(),
            centroid_idx=0,
            ballot_list=ballots,
            weight_vector=weights,
            distance_function=distance,
        )
        self.assertEqual(empty_cost, 0.0)


if __name__ == "__main__":
    unittest.main()
