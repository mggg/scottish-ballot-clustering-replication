"""Describe extracted partitions and the JSON solutions used to publish clustering results."""

from typing import Literal, TypedDict

type EmbeddingName = Literal["borda_pessimistic", "head_to_head"]
type ModelFamily = Literal["cast_ballot", "coordinate", "all_ballot"]


class SolutionMetadata(TypedDict):
    """Source and objective recorded in a supported SOL file."""

    source: str
    model: str
    objective: float


class ExtractedPartition(SolutionMetadata):
    """Common SOL metadata and zero-based cluster labels in ballot order."""

    assignments: list[int]


class CastBallotSolution(ExtractedPartition):
    """Selected ballot indices, with assignments referring to their positions in centers."""

    center_kind: Literal["ballot_index"]
    centers: list[int]


class CoordinateSolution(ExtractedPartition):
    """Center vectors in model cluster order, including any empty cluster slots."""

    center_kind: Literal["coordinates"]
    centers: list[list[int]]


type ExtractedSolution = CastBallotSolution | CoordinateSolution


class BallotCluster(TypedDict):
    """Weighted rankings assigned to a center, using the original candidate and ballot indexing."""

    cluster_index: int
    center_kind: Literal["ranking", "coordinates"]
    center: list[int]
    ballot_indices: list[int]
    ballots: list[list[int]]
    weights: list[float]
    candidates: list[str]


# JSON entries are [ranking_or_coordinates, integer_weight]; validation checks their positions.
type WeightedBallotEntry = list[list[float] | int]
type BallotMemberships = list[list[WeightedBallotEntry]]


class PairedBallotClusters(TypedDict):
    """The two required JSON membership representations, sharing cluster and ballot order."""

    ballot_clusters_in_coordinates: BallotMemberships
    ballot_clusters_from_cvr: BallotMemberships


class CenterMetadata(TypedDict):
    """Election identity, embedding, and center vectors in explicit candidate order."""

    election: str
    candidates: list[str]
    embedding: EmbeddingName
    optimization_model: ModelFamily
    centers: list[list[float]]


class SavedSolution(CenterMetadata, PairedBallotClusters):
    """Published center metadata with both reconstructed or solver-derived membership fields."""
