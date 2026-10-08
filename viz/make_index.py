"""Write viz/elections.csv, the index the STV viz loads: one row per vote table, with the
matching election file, seats, and ward name. Standard library only. Rerun when the data changes:

    python3 viz/make_index.py
"""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COUNCILS = {  # slugs that title-casing gets wrong
    "argyll_bute": "Argyll and Bute",
    "dumgal": "Dumfries and Galloway",
    "edinburgh": "City of Edinburgh",
    "eilean_siar": "Na h-Eileanan Siar",
    "perth_kinross": "Perth and Kinross",
    "sc_borders": "Scottish Borders",
}

rows = []
for table in DATA.glob("scottish_vote_tables/*_cands/*_votes_table.csv"):
    m = re.fullmatch(r"(.+)_(\d{4})_(.+)_votes_table\.csv", table.name)
    if not m:
        raise SystemExit(f"unexpected file name: {table}")
    slug, year, ward_slug = m.groups()
    n = table.parent.name.split("_")[0]
    name = table.name.replace("_votes_table", "")
    # 0-padded folders are canonical; the unpadded ones cover a misspelled 09_cands file name
    tries = [DATA / "scot-elex" / f"{d}_cands" / name for d in (f"{int(n):02d}", n)]
    election = next((p for p in tries if p.exists()), None)
    if election is None:
        raise SystemExit(f"no election file for {table}")
    lines = election.read_text(encoding="utf-8").strip().splitlines()
    ward = lines[-1].strip(' \t",')  # some files double-quote or pad the ward name
    num = re.fullmatch(r"ward(\d+)", ward_slug)
    rows.append({
        "id": name.removesuffix(".csv"),
        "year": year,
        "council": COUNCILS.get(slug, slug.replace("_", " ").title()),
        "ward": ward,
        "seats": int(lines[0].split(",")[1]),
        "candidates": int(n),
        "table": table.relative_to(ROOT).as_posix(),
        "election": election.relative_to(ROOT).as_posix(),
        "_sort": (-int(year), slug, int(num[1]) if num else 999, ward),
    })

assert len({r["id"] for r in rows}) == len(rows), "duplicate election ids"
rows.sort(key=lambda r: r["_sort"])
for r in rows:
    del r["_sort"]
with open(ROOT / "viz/elections.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(f"wrote {len(rows)} elections to viz/elections.csv")
