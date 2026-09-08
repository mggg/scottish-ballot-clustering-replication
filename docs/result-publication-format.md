# Saved solution format

A saved solution is a JSON object containing centers and their ballot clusters. JSON collections
store arrays of these objects; ZIP collections store individual JSON files. Each solution has seven
fields:

| Field                            | Meaning                                                                                |
| -------------------------------- | -------------------------------------------------------------------------------------- |
| `election`                       | Election CSV stem.                                                                     |
| `candidates`                     | Candidate names in source CSV order. CVR candidate ID `i` refers to `candidates[i-1]`. |
| `embedding`                      | `borda_pessimistic` or `head_to_head`.                                                 |
| `optimization_model`             | `cast_ballot`, `all_ballot`, or `coordinate`.                                          |
| `centers`                        | Center coordinate vectors, in saved cluster order. Their count is `k`.                 |
| `ballot_clusters_in_coordinates` | For each cluster, a list of `[coordinate_vector, weight]` entries.                     |
| `ballot_clusters_from_cvr`       | For each cluster, a list of `[CVR_ranking, weight]` entries.                           |

For example:

```json
{
  "election": "example",
  "candidates": ["Alice", "Bob", "Carol"],
  "embedding": "borda_pessimistic",
  "optimization_model": "all_ballot",
  "centers": [
    [2, 0, 0],
    [0, 2, 0]
  ],
  "ballot_clusters_in_coordinates": [
    [
      [[2, 1, 0], 5],
      [[2, 0, 0], 6]
    ],
    [[[0, 2, 0], 4]]
  ],
  "ballot_clusters_from_cvr": [
    [
      [[1, 2], 5],
      [[1], 6]
    ],
    [[[2], 4]]
  ]
}
```

Cluster `r` corresponds to `centers[r]`. Entry `[r][j]` describes the same ballot type and positive
integer weight in both cluster representations. CVR rankings contain one-based candidate IDs, best
first, with omitted candidates left out. These are distinct ranking types, not individual voters.
Frequencies follow the input profile used to build the saved model.

Preserve empty clusters as `[]` in both representations, keeping their center slots. Keep identical
center vectors in their separate slots. Distinct CVR rankings remain separate entries even when
their embeddings coincide. A ranking of length `n-1` and its full extension are one example.

SOL conversion preserves the saved assignments, including how equal-distance ties were resolved. The
[published collection](../data/optimal_cluster_centers/README.md) preserves the selected master SOL
assignments and ballot-entry order, with corrected election and candidate names.

Borda coordinates follow `candidates`: ranked positions earn `n-1, n-2, ..., 0`, and omitted
candidates earn zero. Head-to-head coordinates follow lexicographic pairs of candidate positions:
`(0,1), (0,2), ..., (1,2), ...`. A coordinate is `+1` if the first candidate is preferred, `-1` if
the second is preferred, or `0` if both are omitted. Ranked candidates beat omitted candidates.

The objective is the frequency-weighted sum of raw L1 distances from each stored ballot vector to
its corresponding center.

## Export and load

From the replication repository root:

```sh
uv run python code/analysis_scripts/convert_solution.py result.sol \
  data/scot-elex/03_cands/eilean_siar_2022_ward3.csv result.json
```

Supply the original election CSV and loader ordering. This conversion never solves a model or
reassigns ballots. The lower-level `extract_solution` API and raw SOL-to-CSV export retain their
existing representations for solver workflows.

`load_saved_solution` reads one solution. `load_saved_solutions` accepts one solution, an array, or
a ZIP of individual JSON files and loads the collection into memory. Use `iter_saved_solutions` to
stream ZIP solutions without extracting files, or `iter_archived_solutions` to retain each member's
filename.

`save_solution_archive` writes named solutions to a ZIP and publishes it only after the archive is
complete. Replacing an existing archive requires `overwrite=True`. The [collection
documentation](../data/optimal_cluster_centers/README.md) describes packaging and source
verification.

Both cluster fields are required. Validation checks coordinate embeddings, weights, membership
uniqueness, and cluster counts across the two representations. Solutions missing either field are
rejected.

The `SavedSolution` type in `solution_types.py` requires center metadata and both membership fields.
Runtime validation also checks array lengths, entry positions, candidate ranges, and agreement
between representations.
