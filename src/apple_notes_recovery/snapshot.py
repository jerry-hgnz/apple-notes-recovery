from __future__ import annotations

import shutil
from pathlib import Path

from .common import write_json, write_tsv
from .notes_app import export_account_folders, export_folder_notes


DB_FILENAMES = [
    "NoteStore.sqlite",
    "NoteStore.sqlite-wal",
    "NoteStore.sqlite-shm",
]


def run(args) -> int:
    out_dir = Path(args.out_dir).expanduser().resolve()
    notes_container = Path(args.notes_container).expanduser().resolve()
    raw_dir = out_dir / "raw_live_db"
    manifests_dir = out_dir / "manifests"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []
    missing_files: list[str] = []
    for filename in DB_FILENAMES:
        source = notes_container / filename
        target = raw_dir / filename
        if source.exists():
            shutil.copy2(source, target)
            copied_files.append(str(target))
        else:
            missing_files.append(filename)

    folder_names = export_account_folders(args.account)
    write_tsv(
        manifests_dir / "folder_names.tsv",
        [{"folder_name": folder_name} for folder_name in folder_names],
        ["folder_name"],
    )

    exported_note_count = 0
    notes_manifest_path = None
    if args.folder:
        notes_rows = export_folder_notes(args.account, args.folder)
        notes_manifest_path = manifests_dir / f"{args.folder_manifest_name}.tsv"
        write_tsv(notes_manifest_path, notes_rows, ["note_id", "title", "modification_date"])
        exported_note_count = len(notes_rows)

    summary = {
        "account": args.account,
        "notes_container": str(notes_container),
        "copied_files": copied_files,
        "missing_files": missing_files,
        "folder_count": len(folder_names),
        "exported_folder": args.folder,
        "exported_note_count": exported_note_count,
        "outputs": {
            "raw_live_db": str(raw_dir),
            "folder_names_tsv": str(manifests_dir / "folder_names.tsv"),
            "folder_notes_tsv": str(notes_manifest_path) if notes_manifest_path else None,
        },
    }
    write_json(out_dir / "snapshot_summary.json", summary)
    print(f"snapshot written to {out_dir}")
    return 0
