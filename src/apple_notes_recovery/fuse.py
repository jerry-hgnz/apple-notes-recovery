from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .common import normalize, read_tsv, write_json, write_tsv


def run(args) -> int:
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    folder_display: dict[str, str] = {}
    for row in read_tsv(Path(args.folder_names).expanduser().resolve()):
        folder_display[normalize(row["folder_name"])] = row["folder_name"]

    live_notes = {}
    for row in read_tsv(Path(args.live_titles).expanduser().resolve()):
        match = re.search(r"/p(\d+)$", row["note_id"])
        rowid = int(match.group(1)) if match else None
        live_notes[row["note_id"]] = {
            **row,
            "rowid": rowid,
            "title_norm": normalize(row["title"]),
        }

    mac_by_rowid: dict[int, dict[str, object]] = {}
    if args.mac_mappings:
        for row in read_tsv(Path(args.mac_mappings).expanduser().resolve()):
            rowid = int(row["note_rowid"])
            mac_by_rowid[rowid] = {
                "folder_norm": normalize(row["recovered_folder_name"]),
                "folder_name": row["recovered_folder_name"],
                "source": "mac_carve",
                "confidence": row.get("confidence", "unknown"),
            }

    residual_folder_norm = normalize(args.residual_folder) if args.residual_folder else None
    video_by_note: dict[str, dict[str, object]] = defaultdict(lambda: {"folders": defaultdict(set), "sources": set()})
    ambiguous_live_note_ids: set[str] = set()
    observed_titles_outside_residual: set[str] = set()

    for run_dir_str in args.video_run_dir:
        run_dir = Path(run_dir_str).expanduser().resolve()
        run_name = run_dir.name
        for filename, title_key in [
            ("video_live_exact_unique.tsv", "title_norm"),
            ("video_live_fuzzy_unique.tsv", "observed_title_norm"),
        ]:
            for row in read_tsv(run_dir / filename):
                folder_norm = normalize(row["folder_norm"])
                folder_name = folder_display.get(folder_norm, row["folder_norm"])
                video_by_note[row["note_id"]]["folders"][folder_norm].add(folder_name)
                video_by_note[row["note_id"]]["sources"].add(run_name)
                if residual_folder_norm is None or folder_norm != residual_folder_norm:
                    observed_titles_outside_residual.add(normalize(row[title_key]))

        for row in read_tsv(run_dir / "video_live_exact_ambiguous_live.tsv"):
            if residual_folder_norm is None or normalize(row["folder_norm"]) != residual_folder_norm:
                observed_titles_outside_residual.add(normalize(row["title_norm"]))
            for note_id in row["note_ids"].split(","):
                if note_id:
                    ambiguous_live_note_ids.add(note_id)

        for row in read_tsv(run_dir / "video_live_exact_ambiguous_video.tsv"):
            candidates = [normalize(item) for item in row["video_folder_candidates"].split(",") if item]
            if residual_folder_norm is None or any(item != residual_folder_norm for item in candidates):
                observed_titles_outside_residual.add(normalize(row["title_norm"]))

        for row in read_tsv(run_dir / "video_live_unmatched_pairs.tsv"):
            if residual_folder_norm is None or normalize(row["folder_norm"]) != residual_folder_norm:
                observed_titles_outside_residual.add(normalize(row["title_norm"]))

    direct_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    residual_candidates: list[dict[str, object]] = []

    for note_id, note in live_notes.items():
        evidence_by_folder: defaultdict[str, set[str]] = defaultdict(set)
        source_details: list[str] = []

        if note["rowid"] in mac_by_rowid:
            mac = mac_by_rowid[note["rowid"]]
            evidence_by_folder[mac["folder_norm"]].add(str(mac["source"]))
            source_details.append(f"mac_carve:{mac['folder_name']}:{mac['confidence']}")

        if note_id in video_by_note:
            for folder_norm, folder_names in video_by_note[note_id]["folders"].items():
                evidence_by_folder[folder_norm].add("video")
                for folder_name in sorted(folder_names):
                    source_details.append(f"video:{folder_name}")
            for source in sorted(video_by_note[note_id]["sources"]):
                source_details.append(f"video_run:{source}")

        if not evidence_by_folder:
            residual_candidates.append(
                {
                    "note_id": note_id,
                    "note_rowid": note["rowid"],
                    "title": note["title"],
                    "title_norm": note["title_norm"],
                    "modification_date": note["modification_date"],
                    "title_seen_outside_residual_video": "yes" if note["title_norm"] in observed_titles_outside_residual else "no",
                    "appears_in_ambiguous_live_set": "yes" if note_id in ambiguous_live_note_ids else "no",
                }
            )
            continue

        if len(evidence_by_folder) == 1:
            folder_norm = next(iter(evidence_by_folder))
            direct_rows.append(
                {
                    "note_id": note_id,
                    "note_rowid": note["rowid"],
                    "title": note["title"],
                    "modification_date": note["modification_date"],
                    "assigned_folder_name": folder_display.get(folder_norm, folder_norm),
                    "assigned_folder_norm": folder_norm,
                    "evidence_sources": " | ".join(sorted(set(source_details))),
                }
            )
        else:
            review_rows.append(
                {
                    "reason": "conflicting_direct_evidence",
                    "note_id": note_id,
                    "note_rowid": note["rowid"],
                    "title": note["title"],
                    "modification_date": note["modification_date"],
                    "candidate_folders": " | ".join(folder_display.get(folder, folder) for folder in sorted(evidence_by_folder)),
                    "evidence_sources": " | ".join(sorted(set(source_details))),
                }
            )

    direct_note_ids = {row["note_id"] for row in direct_rows}
    conflict_note_ids = {row["note_id"] for row in review_rows}
    residual_rows = [row for row in residual_candidates if row["note_id"] not in direct_note_ids and row["note_id"] not in conflict_note_ids]

    residual_bucket_rows: list[dict[str, object]] = []
    ambiguous_residual_rows: list[dict[str, object]] = []
    for row in residual_rows:
        if args.residual_folder and row["title_seen_outside_residual_video"] == "no":
            residual_bucket_rows.append(
                row
                | {
                    "hypothesis_folder_name": args.residual_folder,
                    "basis": f"residual_title_never_seen_outside_{normalize(args.residual_folder)}_video",
                }
            )
        else:
            ambiguous_residual_rows.append(row)

    for row in ambiguous_residual_rows:
        review_rows.append(
            {
                "reason": "video_seen_but_not_uniquely_assignable",
                "note_id": row["note_id"],
                "note_rowid": row["note_rowid"],
                "title": row["title"],
                "modification_date": row["modification_date"],
                "candidate_folders": "",
                "evidence_sources": "video_title_seen_without_unique_assignment",
            }
        )

    direct_rows.sort(key=lambda row: (row["assigned_folder_name"], row["title"]))
    residual_bucket_rows.sort(key=lambda row: row["title"])
    review_rows.sort(key=lambda row: (row["reason"], row["title"]))

    write_tsv(
        out_dir / "direct_evidence_assignments.tsv",
        direct_rows,
        ["note_id", "note_rowid", "title", "modification_date", "assigned_folder_name", "assigned_folder_norm", "evidence_sources"],
    )
    write_tsv(
        out_dir / "residual_bucket_inference.tsv",
        residual_bucket_rows,
        ["note_id", "note_rowid", "title", "modification_date", "hypothesis_folder_name", "basis", "title_seen_outside_residual_video", "appears_in_ambiguous_live_set"],
    )
    write_tsv(
        out_dir / "review_needed.tsv",
        review_rows,
        ["reason", "note_id", "note_rowid", "title", "modification_date", "candidate_folders", "evidence_sources"],
    )

    direct_by_folder = Counter(row["assigned_folder_name"] for row in direct_rows)
    summary: dict[str, object] = {
        "live_notes": len(live_notes),
        "direct_evidence_assignments": len(direct_rows),
        "direct_evidence_rate": round(len(direct_rows) / len(live_notes) * 100, 2) if live_notes else 0.0,
        "residual_bucket_folder": args.residual_folder,
        "residual_bucket_inference_count": len(residual_bucket_rows),
        "residual_bucket_inference_rate": round(len(residual_bucket_rows) / len(live_notes) * 100, 2) if live_notes else 0.0,
        "review_needed_count": len(review_rows),
        "review_needed_rate": round(len(review_rows) / len(live_notes) * 100, 2) if live_notes else 0.0,
        "direct_by_folder_top20": dict(direct_by_folder.most_common(20)),
    }
    if args.expected_residual_count is not None:
        summary["expected_residual_count"] = args.expected_residual_count
        summary["residual_minus_expected"] = len(residual_bucket_rows) - args.expected_residual_count

    write_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
