#!/usr/bin/env bash
#SBATCH --job-name=ballot-clustering
#SBATCH --cpus-per-task=12
#SBATCH --mem=64G
#SBATCH --time=1-00:00:00

set -e

manifest=$1
offset=${2:-0}
line_number=$((offset + SLURM_ARRAY_TASK_ID))
IFS=$'\t' read -r file opt_type run_type k < <(sed -n "${line_number}p" "$manifest")
[[ -n "$file" && -n "$opt_type" && -n "$run_type" && "$k" =~ ^[1-9][0-9]*$ ]] || {
    echo "Invalid manifest row $line_number" >&2
    exit 1
}

runtime_options=()
if [[ "$opt_type" != "pam" ]]; then
    runtime_options=(--threads "${SLURM_CPUS_PER_TASK:-1}" --output-dir "${LP_OUTPUT_DIR:-.}")
fi

uv run python code/hpc/run_job.py "${opt_type//_/-}" \
    --file "$file" --run-type "$run_type" -k "$k" \
    "${runtime_options[@]}" \
    --time-limit "${LP_TIME_LIMIT:-82800}"
