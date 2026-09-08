#!/usr/bin/env bash

# Stop on a failed step so later commands do not consume missing or stale results.
set -e

# Run from the repository root. You may optionally supply a new output directory as the first
# argument.
election=data/scot-elex/3_cands/eilean_siar_2022_ward3.csv
output_dir=${1:-example_results}

# Run the cast ballot clustering and save the solution in a format that can be used to warm start
# the all ballot clustering.
uv run -m scottish_ballot_clustering cast-ballot \
    --file "$election" \
    --run-type borda \
    -k 2 \
    --pam-start \
    --output-dir "$output_dir"

cast_dir="$output_dir/IP_solutions/cast_ballot/2_clusters/3_cands"
cast_solution="$cast_dir/eilean_siar_2022_ward3_borda_ip_cast_ballot__NCLUST_2_solution.sol"
saved_dir="$output_dir/saved_solutions"
mkdir -p "$saved_dir"

# Convert the cast ballot solution to our JSON format
uv run python code/analysis_scripts/convert_solution.py \
    "$cast_solution" "$election" "$saved_dir/cast_ballot.json"

# Run the all ballot clustering using the cast ballot solution as a warm start.
# NOTE: warm starting with a cast ballot does not tend to help, but we include it for completeness.
uv run -m scottish_ballot_clustering all-ballot \
    --file "$election" \
    --run-type borda \
    -k 2 \
    --warm-start "$saved_dir/cast_ballot.json" \
    --output-dir "$output_dir"

all_dir="$output_dir/IP_solutions/all_ballot/2_clusters/3_cands"
all_solution="$all_dir/eilean_siar_2022_ward3_borda_ip_all_ballot__NCLUST_2_solution.sol"

# Convert the all ballot solution to our JSON format
uv run python code/analysis_scripts/convert_solution.py \
    "$all_solution" "$election" "$saved_dir/all_ballot.json"

# Extract the solutions to a CSV (not really necessary, but useful for inspection)
uv run python code/analysis_scripts/extract_solutions.py \
    "$output_dir/IP_solutions" "$output_dir/extracted_solutions.csv"

# Summarize the election and clustering results in a single JSON for easier analysis
uv run python code/analysis_scripts/summarize_election.py \
    "$election" --solution "$all_solution" --top-n 5 \
    > "$output_dir/election_and_clusters.json"

# Archive the solutions for sharing
uv run python code/analysis_scripts/archive_solutions.py \
    "$saved_dir" "$output_dir/solutions.zip"
