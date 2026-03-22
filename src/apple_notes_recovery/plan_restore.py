from __future__ import annotations

from pathlib import Path

from .common import read_tsv, write_tsv


def run(args) -> int:
    out_path = Path(args.out).expanduser().resolve()
    rows: list[dict[str, object]] = []

    for row in read_tsv(Path(args.direct).expanduser().resolve()):
        rows.append(
            {
                "note_id": row["note_id"],
                "note_rowid": row["note_rowid"],
                "title": row["title"],
                "target_folder": row["assigned_folder_name"],
                "confidence": "direct",
                "reason": "direct_evidence",
            }
        )

    if args.residual:
        for row in read_tsv(Path(args.residual).expanduser().resolve()):
            rows.append(
                {
                    "note_id": row["note_id"],
                    "note_rowid": row["note_rowid"],
                    "title": row["title"],
                    "target_folder": row["hypothesis_folder_name"],
                    "confidence": "inferred",
                    "reason": row["basis"],
                }
            )

    if args.review:
        for row in read_tsv(Path(args.review).expanduser().resolve()):
            rows.append(
                {
                    "note_id": row["note_id"],
                    "note_rowid": row["note_rowid"],
                    "title": row["title"],
                    "target_folder": args.review_folder,
                    "confidence": "review",
                    "reason": row["reason"],
                }
            )

    rows.sort(key=lambda row: (row["target_folder"], row["title"]))
    write_tsv(out_path, rows, ["note_id", "note_rowid", "title", "target_folder", "confidence", "reason"])
    print(f"restore plan written to {out_path} ({len(rows)} rows)")
    return 0
