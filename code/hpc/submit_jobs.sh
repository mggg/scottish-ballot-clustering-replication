#!/usr/bin/env bash
set -e

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 jobs.tsv [sbatch resource options...]" >&2
    exit 1
fi

manifest=$(realpath "$1")
shift  # Remaining arguments are sbatch options.

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
total=$(awk 'END {print NR}' "$manifest")
concurrent=${LP_CONCURRENT:-8}

[[ "$total" -gt 0 && "$concurrent" =~ ^[1-9][0-9]*$ ]] || {
    echo "Manifest must be nonempty and LP_CONCURRENT must be positive" >&2
    exit 1
}

mkdir -p "$root/logs"

previous_job=""

for ((offset=0; offset<total; offset+=1000)); do
    size=$((total-offset))

    if ((size>1000)); then
        size=1000
    fi

    dependency=()

    if [[ -n "$previous_job" ]]; then
        dependency=("--dependency=afterany:$previous_job")
    fi

    job=$(sbatch --parsable --output="$root/logs/slurm-%A_%a.log" "$@" "${dependency[@]}" \
        --array="1-${size}%${concurrent}" --chdir="$root" \
        "$root/code/hpc/run_array.sh" "$manifest" "$offset")

    previous_job=${job%%;*}

    echo "Submitted $job for rows $((offset+1)) through $((offset+size))"
done
