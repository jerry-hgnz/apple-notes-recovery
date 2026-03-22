from __future__ import annotations

from pathlib import Path

from .common import read_tsv, write_tsv
from .notes_app import move_note


def run(args) -> int:
    plan_path = Path(args.plan).expanduser().resolve()
    success_path = Path(args.success_log).expanduser().resolve()
    failure_path = Path(args.failure_log).expanduser().resolve()

    rows = read_tsv(plan_path)
    if not args.apply:
        print(f"dry-run: {len(rows)} notes would be processed for account {args.account}")
        return 0

    success_rows: list[dict[str, object]] = []
    failure_rows: list[dict[str, object]] = []
    for idx, row in enumerate(rows, start=1):
        ok, result = move_note(args.account, row["note_id"], row["target_folder"])
        payload = {
            "note_id": row["note_id"],
            "note_rowid": row["note_rowid"],
            "title": row["title"],
            "target_folder": row["target_folder"],
            "confidence": row["confidence"],
            "reason": row["reason"],
        }
        if ok:
            success_rows.append(payload | {"result": result})
        else:
            failure_rows.append(payload | {"error": result})
        if idx % 25 == 0 or idx == len(rows):
            print(f"processed={idx}/{len(rows)} ok={ok} last_target={row['target_folder']}")

    write_tsv(success_path, success_rows, ["note_id", "note_rowid", "title", "target_folder", "confidence", "reason", "result"])
    if failure_rows:
        write_tsv(failure_path, failure_rows, ["note_id", "note_rowid", "title", "target_folder", "confidence", "reason", "error"])
    print(f"restore finished: success={len(success_rows)} failure={len(failure_rows)}")
    return 0
