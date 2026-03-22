from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .common import normalize, write_json


SECTION_TITLES = {
    "folders",
    "edit",
    "quicknotes",
    "shared",
    "icloud",
    "allicloud",
    "notes",
    "pinned",
    "previous30days",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "2025",
    "2026",
}


def looks_like_subtitle(text: str) -> bool:
    t = normalize(text)
    if not t:
        return True
    if t in SECTION_TITLES:
        return True
    if re.match(r"^20\d{2}[/-]", t):
        return True
    if "http" in t or ".com" in t:
        return True
    if re.match(r"^\d{1,2}[:./-]\d{1,2}", t):
        return True
    if re.match(r"^[\d,]+$", t):
        return True
    return False


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(a=a, b=b).ratio()


@dataclass
class OCRLine:
    time: float
    text: str
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    confidence: float

    @property
    def norm(self) -> str:
        return normalize(self.text)


def load_ocr(path: Path) -> list[OCRLine]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        OCRLine(
            time=float(item["time"]),
            text=item["text"],
            min_x=float(item["minX"]),
            min_y=float(item["minY"]),
            max_x=float(item["maxX"]),
            max_y=float(item["maxY"]),
            confidence=float(item["confidence"]),
        )
        for item in raw
    ]


def extract_video_pairs(lines: list[OCRLine]) -> tuple[set[tuple[str, str]], dict[float, dict[str, object]]]:
    by_time: dict[float, list[OCRLine]] = defaultdict(list)
    for line in lines:
        by_time[line.time].append(line)

    observed_pairs: set[tuple[str, str]] = set()
    frame_debug: dict[float, dict[str, object]] = {}

    for time, frame_lines in sorted(by_time.items()):
        candidates = [
            line
            for line in frame_lines
            if line.confidence >= 0.45
            and 0.24 <= line.min_x <= 0.46
            and line.max_y >= 0.93
            and normalize(line.text) not in SECTION_TITLES
        ]
        if not candidates:
            continue
        folder_line = max(candidates, key=lambda line: (line.max_y - line.min_y, len(line.text)))
        folder = folder_line.norm

        titles: list[str] = []
        for line in frame_lines:
            if line.confidence < 0.45:
                continue
            in_middle = 0.24 <= line.min_x <= 0.46 and 0.34 <= line.max_y <= 0.92
            in_right_title = 0.52 <= line.min_x <= 0.78 and 0.83 <= line.max_y <= 0.93
            if not (in_middle or in_right_title):
                continue
            if looks_like_subtitle(line.text):
                continue
            if len(line.norm) <= 1:
                continue
            titles.append(line.text)
            observed_pairs.add((folder, line.norm))

        frame_debug[time] = {"folder": folder_line.text, "titles": titles}

    return observed_pairs, frame_debug


def load_live_titles(path: Path) -> tuple[list[dict[str, str]], dict[str, list[dict[str, str]]]]:
    rows: list[dict[str, str]] = []
    by_title: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            norm_title = normalize(row["title"])
            if not norm_title:
                continue
            clean = {
                "note_id": row["note_id"],
                "title": row["title"],
                "title_norm": norm_title,
                "modification_date": row.get("modification_date", ""),
            }
            rows.append(clean)
            by_title[norm_title].append(clean)
    return rows, by_title


def load_known_folders(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            folder_name = row["folder_name"].strip()
            if folder_name:
                out[normalize(folder_name)] = folder_name
    return out


def canonicalize_folder(folder_norm: str, known_folders: dict[str, str]) -> tuple[str, str | None, float | None]:
    if not known_folders:
        return folder_norm, None, None
    if folder_norm in known_folders:
        return folder_norm, known_folders[folder_norm], 1.0
    scored = sorted(
        ((known_norm, similarity(folder_norm, known_norm)) for known_norm in known_folders),
        key=lambda item: item[1],
        reverse=True,
    )
    if not scored:
        return folder_norm, None, None
    best_norm, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    if best_score >= 0.84 or (best_score >= 0.75 and second_score <= best_score - 0.12):
        return best_norm, known_folders[best_norm], best_score
    return folder_norm, None, best_score


def smooth_frame_folders(
    frame_debug: dict[float, dict[str, object]],
    known_folders: dict[str, str],
) -> tuple[set[tuple[str, str]], dict[str, dict[str, object]], dict[float, dict[str, object]]]:
    sorted_times = sorted(frame_debug.keys())
    folder_aliases: dict[str, dict[str, object]] = {}
    resolved_frames: list[dict[str, object]] = []

    for time in sorted_times:
        item = frame_debug[time]
        raw_folder = normalize(str(item.get("folder", "")))
        canonical_folder, display_name, best_score = canonicalize_folder(raw_folder, known_folders)
        recognized = bool(known_folders and canonical_folder in known_folders)
        resolved_frames.append(
            {
                "time": time,
                "raw_folder_norm": raw_folder,
                "raw_folder_text": item.get("folder", ""),
                "titles": item.get("titles", []),
                "canonical_folder_norm": canonical_folder,
                "canonical_folder_name": display_name,
                "best_score": best_score,
                "recognized": recognized,
                "smoothed_from_previous": False,
            }
        )
        if recognized and canonical_folder != raw_folder:
            folder_aliases[raw_folder] = {
                "canonical_folder_norm": canonical_folder,
                "canonical_folder_name": display_name,
                "similarity": round(best_score or 0.0, 4),
            }

    last_recognized_folder: str | None = None
    last_recognized_name: str | None = None
    last_recognized_time: float | None = None
    for frame in resolved_frames:
        if frame["recognized"]:
            last_recognized_folder = str(frame["canonical_folder_norm"])
            last_recognized_name = str(frame["canonical_folder_name"])
            last_recognized_time = float(frame["time"])
            continue
        if last_recognized_folder is not None and last_recognized_time is not None and (float(frame["time"]) - last_recognized_time) <= 12.0:
            frame["canonical_folder_norm"] = last_recognized_folder
            frame["canonical_folder_name"] = last_recognized_name
            frame["recognized"] = True
            frame["smoothed_from_previous"] = True
            raw_folder = str(frame["raw_folder_norm"])
            folder_aliases[raw_folder] = {
                "canonical_folder_norm": last_recognized_folder,
                "canonical_folder_name": last_recognized_name,
                "similarity": None,
                "strategy": "carry_forward",
            }

    observed_pairs: set[tuple[str, str]] = set()
    for frame in resolved_frames:
        if not frame["recognized"]:
            continue
        folder = str(frame["canonical_folder_norm"])
        for title_text in frame["titles"]:
            title_norm = normalize(title_text)
            if title_norm and len(title_norm) > 1:
                observed_pairs.add((folder, title_norm))

    new_frame_debug: dict[float, dict[str, object]] = {}
    for frame in resolved_frames:
        new_frame_debug[float(frame["time"])] = {
            "folder": frame["raw_folder_text"],
            "resolved_folder_norm": frame["canonical_folder_norm"],
            "resolved_folder_name": frame["canonical_folder_name"],
            "recognized": frame["recognized"],
            "smoothed_from_previous": frame["smoothed_from_previous"],
            "titles": frame["titles"],
        }

    return observed_pairs, folder_aliases, new_frame_debug


def write_dicts(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def run(args) -> int:
    ocr_path = Path(args.ocr_json).expanduser().resolve()
    live_titles_path = Path(args.live_titles).expanduser().resolve()
    output_dir = Path(args.out_dir).expanduser().resolve()
    known_folders_path = Path(args.known_folders).expanduser().resolve() if args.known_folders else None
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = load_ocr(ocr_path)
    observed_pairs, frame_debug = extract_video_pairs(lines)
    live_rows, live_by_title = load_live_titles(live_titles_path)
    known_folders = load_known_folders(known_folders_path)
    folder_aliases = {}
    if known_folders:
        observed_pairs, folder_aliases, frame_debug = smooth_frame_folders(frame_debug, known_folders)

    title_to_video_folders: dict[str, set[str]] = defaultdict(set)
    observed_by_folder = Counter()
    for folder, title in observed_pairs:
        title_to_video_folders[title].add(folder)
        observed_by_folder[folder] += 1

    exact_unique: list[dict[str, object]] = []
    exact_ambiguous_live: list[dict[str, object]] = []
    exact_ambiguous_video: list[dict[str, object]] = []
    unmatched_video_pairs: list[tuple[str, str]] = []

    for folder, title in sorted(observed_pairs):
        live_candidates = live_by_title.get(title, [])
        video_folder_candidates = title_to_video_folders[title]
        if len(video_folder_candidates) > 1:
            exact_ambiguous_video.append(
                {
                    "folder_norm": folder,
                    "title_norm": title,
                    "video_folder_candidates": ",".join(sorted(video_folder_candidates)),
                    "live_candidate_count": len(live_candidates),
                }
            )
            continue
        if len(live_candidates) == 1:
            exact_unique.append(
                {
                    "folder_norm": folder,
                    "title_norm": title,
                    "note_id": live_candidates[0]["note_id"],
                    "live_title": live_candidates[0]["title"],
                    "modification_date": live_candidates[0]["modification_date"],
                }
            )
        elif len(live_candidates) > 1:
            exact_ambiguous_live.append(
                {
                    "folder_norm": folder,
                    "title_norm": title,
                    "live_candidate_count": len(live_candidates),
                    "note_ids": ",".join(candidate["note_id"] for candidate in live_candidates),
                }
            )
        else:
            unmatched_video_pairs.append((folder, title))

    used_live_title_norms = {row["title_norm"] for row in exact_unique}
    fuzzy_unique: list[dict[str, object]] = []
    still_unmatched: list[tuple[str, str]] = []
    all_live_title_norms = list(live_by_title.keys())

    for folder, title in unmatched_video_pairs:
        if len(title_to_video_folders[title]) > 1:
            still_unmatched.append((folder, title))
            continue
        scored = sorted(
            (
                (
                    candidate_title,
                    similarity(title, candidate_title),
                    len(live_by_title[candidate_title]),
                )
                for candidate_title in all_live_title_norms
                if candidate_title not in used_live_title_norms
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        if not scored:
            still_unmatched.append((folder, title))
            continue
        best_title, best_score, best_live_count = scored[0]
        second_score = scored[1][1] if len(scored) > 1 else 0.0
        if best_live_count == 1 and best_score >= 0.93 and second_score <= best_score - 0.08:
            live_candidate = live_by_title[best_title][0]
            fuzzy_unique.append(
                {
                    "folder_norm": folder,
                    "observed_title_norm": title,
                    "matched_live_title_norm": best_title,
                    "note_id": live_candidate["note_id"],
                    "live_title": live_candidate["title"],
                    "modification_date": live_candidate["modification_date"],
                    "similarity": round(best_score, 4),
                    "second_best_similarity": round(second_score, 4),
                }
            )
            used_live_title_norms.add(best_title)
        else:
            still_unmatched.append((folder, title))

    assigned_note_ids = {row["note_id"] for row in exact_unique} | {row["note_id"] for row in fuzzy_unique}
    unassigned_live_notes = [row for row in live_rows if row["note_id"] not in assigned_note_ids]

    summary = {
        "video_observed_pairs": len(observed_pairs),
        "video_observed_folders": len(observed_by_folder),
        "live_notes": len(live_rows),
        "exact_unique_assignments": len(exact_unique),
        "exact_ambiguous_live": len(exact_ambiguous_live),
        "exact_ambiguous_video": len(exact_ambiguous_video),
        "fuzzy_unique_assignments": len(fuzzy_unique),
        "assigned_total": len(exact_unique) + len(fuzzy_unique),
        "assigned_rate_vs_live_notes": round((len(exact_unique) + len(fuzzy_unique)) / len(live_rows) * 100, 2) if live_rows else 0.0,
        "residual_bucket_size": len(unassigned_live_notes),
        "observed_by_folder": dict(sorted(observed_by_folder.items(), key=lambda item: (-item[1], item[0]))),
        "folder_aliases": folder_aliases,
    }

    write_json(output_dir / "video_frame_debug.json", frame_debug)
    write_json(output_dir / "video_live_summary.json", summary)
    write_dicts(output_dir / "video_live_exact_unique.tsv", exact_unique, ["folder_norm", "title_norm", "note_id", "live_title", "modification_date"])
    write_dicts(output_dir / "video_live_exact_ambiguous_live.tsv", exact_ambiguous_live, ["folder_norm", "title_norm", "live_candidate_count", "note_ids"])
    write_dicts(output_dir / "video_live_exact_ambiguous_video.tsv", exact_ambiguous_video, ["folder_norm", "title_norm", "video_folder_candidates", "live_candidate_count"])
    write_dicts(output_dir / "video_live_fuzzy_unique.tsv", fuzzy_unique, ["folder_norm", "observed_title_norm", "matched_live_title_norm", "note_id", "live_title", "modification_date", "similarity", "second_best_similarity"])
    with (output_dir / "video_live_unmatched_pairs.tsv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["folder_norm", "title_norm"])
        writer.writerows(sorted(still_unmatched))
    write_dicts(output_dir / "video_live_unassigned_notes.tsv", unassigned_live_notes, ["note_id", "title", "title_norm", "modification_date"])
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
