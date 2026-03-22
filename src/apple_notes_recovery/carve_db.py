#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


UUID_RE = re.compile(
    rb"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}"
)

COL_Z_ENT = 1
COL_Z_CREATIONDATE = 79
COL_Z_MODIFICATIONDATE = 89
COL_Z_IDENTIFIER = 117
COL_Z_TITLE = 132
COL_Z_TITLE1 = 153
COL_Z_TITLE2 = 164
COL_Z_FOLDER = 60


@dataclass
class NoteInfo:
    rowid: int
    identifier: str
    title: str
    current_folder_pk: int | None
    current_folder_name: str


def read_varint(buf: bytes, start: int, limit: int | None = None) -> tuple[int, int] | None:
    if limit is None:
        limit = len(buf)
    value = 0
    for i in range(9):
        pos = start + i
        if pos >= limit:
            return None
        byte = buf[pos]
        if i == 8:
            value = (value << 8) | byte
            return value, pos + 1
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            return value, pos + 1
    return None


def serial_length(serial_type: int) -> int:
    if serial_type == 0:
        return 0
    if serial_type == 1:
        return 1
    if serial_type == 2:
        return 2
    if serial_type == 3:
        return 3
    if serial_type == 4:
        return 4
    if serial_type == 5:
        return 6
    if serial_type == 6:
        return 8
    if serial_type == 7:
        return 8
    if serial_type in (8, 9):
        return 0
    if serial_type >= 12:
        return (serial_type - 12) // 2
    raise ValueError(f"Unsupported serial type: {serial_type}")


def decode_value(serial_type: int, raw: bytes) -> Any:
    if serial_type == 0:
        return None
    if serial_type == 1:
        return int.from_bytes(raw, "big", signed=True)
    if serial_type == 2:
        return int.from_bytes(raw, "big", signed=True)
    if serial_type == 3:
        return int.from_bytes(raw, "big", signed=True)
    if serial_type == 4:
        return int.from_bytes(raw, "big", signed=True)
    if serial_type == 5:
        return int.from_bytes(raw, "big", signed=True)
    if serial_type == 6:
        return int.from_bytes(raw, "big", signed=True)
    if serial_type == 7:
        return struct.unpack(">d", raw)[0]
    if serial_type == 8:
        return 0
    if serial_type == 9:
        return 1
    if serial_type >= 12:
        if serial_type % 2 == 0:
            return raw
        return raw.decode("utf-8", "replace")
    raise ValueError(f"Unsupported serial type: {serial_type}")


def table_leaf_local(payload_size: int, usable_size: int) -> tuple[int, bool]:
    max_local = usable_size - 35
    min_local = ((usable_size - 12) * 32 // 255) - 23
    if payload_size <= max_local:
        return payload_size, False
    local = min_local + ((payload_size - min_local) % (usable_size - 4))
    if local > max_local:
        local = min_local
    return local, True


def read_overflow_payload(
    file_bytes: bytes,
    first_page_no: int,
    needed: int,
    page_size: int,
    reserved: int,
) -> bytes | None:
    max_page = len(file_bytes) // page_size
    next_page = first_page_no
    chunk_size = page_size - reserved - 4
    out = bytearray()
    seen: set[int] = set()
    while next_page and needed > 0:
        if next_page < 1 or next_page > max_page or next_page in seen:
            return None
        seen.add(next_page)
        page = file_bytes[(next_page - 1) * page_size : next_page * page_size]
        next_page = int.from_bytes(page[:4], "big")
        take = min(needed, chunk_size)
        out.extend(page[4 : 4 + take])
        needed -= take
    if needed > 0:
        return None
    return bytes(out)


def parse_record(payload: bytes) -> tuple[dict[int, Any], dict[int, tuple[int, int]]]:
    header_info = read_varint(payload, 0)
    if header_info is None:
        raise ValueError("Missing record header size")
    header_size, header_pos = header_info
    if header_size > len(payload) or header_size < header_pos:
        raise ValueError("Invalid record header size")

    serial_types: list[int] = []
    while header_pos < header_size:
        item = read_varint(payload, header_pos, header_size)
        if item is None:
            raise ValueError("Truncated serial type list")
        serial_type, header_pos = item
        serial_types.append(serial_type)

    data_pos = header_size
    values: dict[int, Any] = {}
    offsets: dict[int, tuple[int, int]] = {}
    for col_index, serial_type in enumerate(serial_types):
        raw_len = serial_length(serial_type)
        raw = payload[data_pos : data_pos + raw_len]
        if len(raw) != raw_len:
            raise ValueError("Truncated record payload")
        if col_index in {
            COL_Z_ENT,
            COL_Z_CREATIONDATE,
            COL_Z_MODIFICATIONDATE,
            COL_Z_IDENTIFIER,
            COL_Z_TITLE,
            COL_Z_TITLE1,
            COL_Z_TITLE2,
            COL_Z_FOLDER,
        }:
            values[col_index] = decode_value(serial_type, raw)
            offsets[col_index] = (data_pos, raw_len)
        data_pos += raw_len
    return values, offsets


def interval_contains(intervals: list[tuple[int, int]], pos: int) -> bool:
    for start, end in intervals:
        if start <= pos < end:
            return True
    return False


def coalesce_title(values: dict[int, Any]) -> str:
    for key in (COL_Z_TITLE1, COL_Z_TITLE, COL_Z_TITLE2):
        value = values.get(key)
        if isinstance(value, str) and value:
            return value.replace("\x00", "")
    return ""


def load_state(conn: sqlite3.Connection) -> tuple[dict[int, str], dict[str, NoteInfo], dict[int, NoteInfo]]:
    folder_rows = conn.execute(
        """
        select
          Z_PK,
          coalesce(ZTITLE2, ZTITLE1, ZTITLE, ZNAME, ZUSERTITLE)
        from ZICCLOUDSYNCINGOBJECT
        where Z_ENT = 14
        """
    ).fetchall()
    folder_names = {int(pk): (name or f"Folder:{pk}") for pk, name in folder_rows}

    note_rows = conn.execute(
        """
        select
          Z_PK,
          ZIDENTIFIER,
          coalesce(ZTITLE1, ZTITLE, ''),
          ZFOLDER
        from ZICCLOUDSYNCINGOBJECT
        where Z_ENT = 11 and ZIDENTIFIER is not null
        """
    ).fetchall()
    notes_by_identifier: dict[str, NoteInfo] = {}
    notes_by_rowid: dict[int, NoteInfo] = {}
    for rowid, identifier, title, folder_pk in note_rows:
        rowid = int(rowid)
        folder_name = folder_names.get(folder_pk, f"Folder:{folder_pk}") if folder_pk is not None else ""
        note = NoteInfo(
            rowid=rowid,
            identifier=identifier,
            title=title or "",
            current_folder_pk=folder_pk,
            current_folder_name=folder_name,
        )
        notes_by_identifier[identifier] = note
        notes_by_rowid[rowid] = note
    return folder_names, notes_by_identifier, notes_by_rowid


def get_leaf_pages(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        """
        select pageno
        from dbstat
        where name = 'ZICCLOUDSYNCINGOBJECT'
          and pagetype = 'leaf'
        order by pageno
        """
    ).fetchall()
    return [int(row[0]) for row in rows]


def read_reserved_bytes(db_path: Path) -> int:
    header = db_path.read_bytes()[:100]
    if len(header) < 21:
        return 0
    return header[20]


def build_live_intervals(
    page: bytes,
    page_no: int,
    page_size: int,
    usable_size: int,
) -> tuple[list[tuple[int, int]], int]:
    base = 100 if page_no == 1 else 0
    if page[base] != 0x0D:
        return [], base
    cell_count = int.from_bytes(page[base + 3 : base + 5], "big")
    intervals: list[tuple[int, int]] = []
    for idx in range(cell_count):
        ptr_off = base + 8 + idx * 2
        cell_start = int.from_bytes(page[ptr_off : ptr_off + 2], "big")
        if cell_start <= 0 or cell_start >= page_size:
            continue
        header_1 = read_varint(page, cell_start)
        if header_1 is None:
            continue
        payload_size, after_payload_size = header_1
        header_2 = read_varint(page, after_payload_size)
        if header_2 is None:
            continue
        _, after_rowid = header_2
        local_size, has_overflow = table_leaf_local(payload_size, usable_size)
        cell_size = (after_rowid - cell_start) + local_size + (4 if has_overflow else 0)
        intervals.append((cell_start, min(page_size, cell_start + cell_size)))
    scan_start = base + 8 + cell_count * 2
    return intervals, scan_start


def iter_gap_offsets(
    intervals: list[tuple[int, int]],
    scan_start: int,
    page_size: int,
) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    cursor = scan_start
    for start, end in sorted(intervals):
        if cursor < start:
            out.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < page_size:
        out.append((cursor, page_size))
    return out


def parse_candidate_from_start(
    page: bytes,
    file_bytes: bytes,
    page_no: int,
    start: int,
    page_size: int,
    usable_size: int,
    notes_by_rowid: dict[int, NoteInfo],
    folder_names: dict[int, str],
) -> tuple[dict[str, Any], dict[int, tuple[int, int]]] | None:
    header_1 = read_varint(page, start)
    if header_1 is None:
        return None
    payload_size, after_payload_size = header_1
    if payload_size <= 0 or payload_size > 5_000_000:
        return None
    header_2 = read_varint(page, after_payload_size)
    if header_2 is None:
        return None
    rowid, after_rowid = header_2
    expected_note = notes_by_rowid.get(rowid)
    if expected_note is None:
        return None

    local_size, has_overflow = table_leaf_local(payload_size, usable_size)
    cell_size = (after_rowid - start) + local_size + (4 if has_overflow else 0)
    if start + cell_size > page_size:
        return None

    payload_start = after_rowid
    local_payload = page[payload_start : payload_start + local_size]
    if len(local_payload) != local_size:
        return None
    full_payload = local_payload
    if has_overflow:
        overflow_ptr = int.from_bytes(
            page[payload_start + local_size : payload_start + local_size + 4],
            "big",
        )
        remaining = payload_size - local_size
        overflow = read_overflow_payload(
            file_bytes,
            overflow_ptr,
            remaining,
            page_size,
            page_size - usable_size,
        )
        if overflow is None:
            return None
        full_payload = local_payload + overflow
    if len(full_payload) < payload_size:
        return None

    try:
        values, offsets = parse_record(full_payload[:payload_size])
    except ValueError:
        return None

    if values.get(COL_Z_ENT) != 11:
        return None
    identifier = values.get(COL_Z_IDENTIFIER)
    if identifier != expected_note.identifier:
        return None

    old_folder_pk = values.get(COL_Z_FOLDER)
    if not isinstance(old_folder_pk, int):
        return None

    title = coalesce_title(values)
    title_matches = bool(title and expected_note.title and title == expected_note.title)
    identifier_offset = offsets.get(COL_Z_IDENTIFIER, (-1, -1))[0]
    if identifier_offset >= 0 and identifier_offset < local_size:
        absolute_identifier_offset = payload_start + identifier_offset
    else:
        absolute_identifier_offset = -1

    return ({
        "note_rowid": expected_note.rowid,
        "identifier": expected_note.identifier,
        "current_title": expected_note.title,
        "current_folder_pk": expected_note.current_folder_pk,
        "current_folder_name": expected_note.current_folder_name,
        "recovered_folder_pk": old_folder_pk,
        "recovered_folder_name": folder_names.get(old_folder_pk, f"Folder:{old_folder_pk}"),
        "recovered_title": title,
        "title_matches": title_matches,
        "page_no": page_no,
        "start_offset": start,
        "identifier_offset": absolute_identifier_offset,
        "payload_size": payload_size,
        "modification_date": values.get(COL_Z_MODIFICATIONDATE),
        "creation_date": values.get(COL_Z_CREATIONDATE),
        "has_overflow": has_overflow,
    }, offsets)


def find_candidates(
    db_path: Path,
    folder_names: dict[int, str],
    notes_by_identifier: dict[str, NoteInfo],
    notes_by_rowid: dict[int, NoteInfo],
    lookback: int,
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    page_size = int(conn.execute("pragma page_size").fetchone()[0])
    reserved = read_reserved_bytes(db_path)
    usable_size = page_size - reserved
    leaf_pages = get_leaf_pages(conn)
    conn.close()

    file_bytes = db_path.read_bytes()
    candidates: list[dict[str, Any]] = []
    seen_keys: set[tuple[int, int, int, int]] = set()

    for page_no in leaf_pages:
        page = file_bytes[(page_no - 1) * page_size : page_no * page_size]
        if len(page) != page_size:
            continue
        intervals, scan_start = build_live_intervals(page, page_no, page_size, usable_size)
        base = 100 if page_no == 1 else 0
        for match in UUID_RE.finditer(page):
            hit_offset = match.start()
            if hit_offset < base or interval_contains(intervals, hit_offset):
                continue
            identifier = match.group().decode("ascii", "ignore")
            note = notes_by_identifier.get(identifier)
            if note is None:
                continue
            window_start = max(base + 8, hit_offset - lookback)
            window_end = hit_offset + 1
            for start in range(window_start, window_end):
                if interval_contains(intervals, start):
                    continue
                parsed = parse_candidate_from_start(
                    page=page,
                    file_bytes=file_bytes,
                    page_no=page_no,
                    start=start,
                    page_size=page_size,
                    usable_size=usable_size,
                    notes_by_rowid=notes_by_rowid,
                    folder_names=folder_names,
                )
                if parsed is None:
                    continue
                candidate, offsets = parsed
                identifier_offset = offsets.get(COL_Z_IDENTIFIER, (-1, -1))[0]
                if identifier_offset < 0 or identifier_offset >= table_leaf_local(candidate["payload_size"], usable_size)[0]:
                    continue
                if candidate["identifier_offset"] != hit_offset:
                    continue
                key = (
                    candidate["note_rowid"],
                    candidate["page_no"],
                    candidate["start_offset"],
                    candidate["recovered_folder_pk"],
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                candidates.append(candidate)

        for gap_start, gap_end in iter_gap_offsets(intervals, scan_start, page_size):
            for start in range(gap_start, gap_end):
                parsed = parse_candidate_from_start(
                    page=page,
                    file_bytes=file_bytes,
                    page_no=page_no,
                    start=start,
                    page_size=page_size,
                    usable_size=usable_size,
                    notes_by_rowid=notes_by_rowid,
                    folder_names=folder_names,
                )
                if parsed is None:
                    continue
                candidate, _ = parsed
                key = (
                    candidate["note_rowid"],
                    candidate["page_no"],
                    candidate["start_offset"],
                    candidate["recovered_folder_pk"],
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                candidates.append(candidate)
    return candidates


def choose_best_mappings(
    candidates: list[dict[str, Any]],
    trash_folder_pk: int = 2242,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[int(candidate["note_rowid"])].append(candidate)

    best_rows: list[dict[str, Any]] = []
    ambiguous_rows: list[dict[str, Any]] = []

    for note_rowid, items in grouped.items():
        useful = [item for item in items if item["recovered_folder_pk"] != trash_folder_pk]
        target_items = useful or items
        distinct_folders = {
            (item["recovered_folder_pk"], item["recovered_folder_name"])
            for item in target_items
        }

        def sort_key(item: dict[str, Any]) -> tuple[int, float, int, int]:
            return (
                1 if item["recovered_folder_pk"] != trash_folder_pk else 0,
                float(item["modification_date"] or float("-inf")),
                1 if item["title_matches"] else 0,
                -int(item["page_no"]),
            )

        best = sorted(target_items, key=sort_key, reverse=True)[0]
        best = dict(best)
        best["candidate_count"] = len(items)
        best["distinct_folder_count"] = len(distinct_folders)
        if len(distinct_folders) == 1:
            best["confidence"] = "high" if best["title_matches"] else "medium"
        else:
            best["confidence"] = "ambiguous"

        best_rows.append(best)
        if len(distinct_folders) > 1:
            by_folder = Counter(
                f"{item['recovered_folder_pk']}::{item['recovered_folder_name']}"
                for item in target_items
            )
            ambiguous_rows.append(
                {
                    "note_rowid": note_rowid,
                    "identifier": best["identifier"],
                    "current_title": best["current_title"],
                    "folders": json.dumps(by_folder, ensure_ascii=False, sort_keys=True),
                    "candidate_count": len(items),
                }
            )

    best_rows.sort(key=lambda item: (item["confidence"], item["recovered_folder_name"], item["current_title"]))
    ambiguous_rows.sort(key=lambda item: item["note_rowid"])
    return best_rows, ambiguous_rows


def write_tsv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    def clean(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace("\x00", "")
        return value

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: clean(row.get(name, "")) for name in fieldnames})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        required=True,
        help="Path to a copied NoteStore.sqlite",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Directory for exported mapping files",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=1600,
        help="How far backwards from a UUID hit to search for a stale row start",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    folder_names, notes_by_identifier, notes_by_rowid = load_state(conn)
    conn.close()

    candidates = find_candidates(
        db_path=db_path,
        folder_names=folder_names,
        notes_by_identifier=notes_by_identifier,
        notes_by_rowid=notes_by_rowid,
        lookback=args.lookback,
    )
    best_rows, ambiguous_rows = choose_best_mappings(candidates)
    restorable_rows = [
        row
        for row in best_rows
        if row["recovered_folder_pk"] in folder_names and row["recovered_folder_pk"] != 2242
    ]
    review_rows = [
        row
        for row in best_rows
        if row["recovered_folder_pk"] not in folder_names or row["recovered_folder_pk"] == 2242
    ]

    candidate_fields = [
        "note_rowid",
        "identifier",
        "current_title",
        "current_folder_pk",
        "current_folder_name",
        "recovered_folder_pk",
        "recovered_folder_name",
        "recovered_title",
        "title_matches",
        "page_no",
        "start_offset",
        "identifier_offset",
        "payload_size",
        "modification_date",
        "creation_date",
        "has_overflow",
    ]
    best_fields = [
        "note_rowid",
        "identifier",
        "current_title",
        "current_folder_pk",
        "current_folder_name",
        "recovered_folder_pk",
        "recovered_folder_name",
        "recovered_title",
        "title_matches",
        "confidence",
        "candidate_count",
        "distinct_folder_count",
        "page_no",
        "start_offset",
        "identifier_offset",
        "modification_date",
        "creation_date",
    ]
    ambiguous_fields = [
        "note_rowid",
        "identifier",
        "current_title",
        "folders",
        "candidate_count",
    ]

    write_tsv(out_dir / "recovered_candidates.tsv", candidates, candidate_fields)
    write_tsv(out_dir / "recovered_best_mappings.tsv", best_rows, best_fields)
    write_tsv(out_dir / "recovered_restorable_mappings.tsv", restorable_rows, best_fields)
    write_tsv(out_dir / "recovered_review_needed.tsv", review_rows, best_fields)
    write_tsv(out_dir / "recovered_ambiguous_notes.tsv", ambiguous_rows, ambiguous_fields)

    folder_counter = Counter(row["recovered_folder_name"] for row in best_rows)
    confidence_counter = Counter(row["confidence"] for row in best_rows)
    restorable_folder_counter = Counter(row["recovered_folder_name"] for row in restorable_rows)
    summary = {
        "notes_total": len(notes_by_identifier),
        "candidate_rows": len(candidates),
        "notes_recovered": len(best_rows),
        "notes_restorable": len(restorable_rows),
        "notes_needing_review": len(review_rows),
        "confidence_breakdown": confidence_counter,
        "folder_breakdown": folder_counter.most_common(),
        "restorable_folder_breakdown": restorable_folder_counter.most_common(),
        "lookback": args.lookback,
        "outputs": {
            "candidates_tsv": str(out_dir / "recovered_candidates.tsv"),
            "best_mappings_tsv": str(out_dir / "recovered_best_mappings.tsv"),
            "restorable_mappings_tsv": str(out_dir / "recovered_restorable_mappings.tsv"),
            "review_needed_tsv": str(out_dir / "recovered_review_needed.tsv"),
            "ambiguous_notes_tsv": str(out_dir / "recovered_ambiguous_notes.tsv"),
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
