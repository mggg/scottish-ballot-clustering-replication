# Published cluster solutions

The collection contains 14,885 solutions grouped into three ZIPs by cluster count. Each solution
preserves the model's saved SOL assignments including how distance ties were resolved and the order
of ballot entries. The [election profiles](../scot-elex/README.md) describe the inputs, and the
[saved JSON format](../../docs/result-publication-format.md) explains how centers and memberships
are represented.

Within each archive, paths such as `1_clusters/6_candidates/<experiment>.json` group solutions by
candidate count. The three ZIPs occupy about 165 MiB and expand to 4.6 GiB:

| Archive                          | Results | Compressed size |
| -------------------------------- | ------: | --------------: |
| [1_clusters.zip](1_clusters.zip) |   6,420 |       77.32 MiB |
| [2_clusters.zip](2_clusters.zip) |   6,270 |       76.55 MiB |
| [3_clusters.zip](3_clusters.zip) |   2,195 |       10.74 MiB |

## Reading and packaging

When processing a large collection, you can read and validate one solution at a time directly from
the ZIP:

```python
from scottish_ballot_clustering.saved_solutions import iter_saved_solutions

for solution in iter_saved_solutions("data/optimal_cluster_centers/1_clusters.zip"):
    print(solution["election"], solution["centers"])
```

To retain filenames as well, use `iter_archived_solutions`. Both iterators keep only one decoded
solution at a time, whereas `load_saved_solutions` loads the entire collection into memory.

To build an archive from loose solution JSON files, run the packaging command from the repository
root:

```sh
uv run python code/analysis_scripts/archive_solutions.py \
  path/to/1_clusters data/optimal_cluster_centers/1_clusters.zip --overwrite
```

The source files remain in place after packaging, and their enclosing directory is included in the
archive's member paths. If an existing archive should be preserved, omit `--overwrite`. When
preparing the JSON inputs, convert the SOL files directly because reconstructing memberships from
centers can assign tied ballots differently.