from __future__ import annotations

import importlib.resources
import subprocess
from pathlib import Path


def bundled_swift_source() -> Path:
    return Path(str(importlib.resources.files("apple_notes_recovery.tools").joinpath("video_ocr_interval.swift")))


def ensure_compiled_binary(build_dir: Path, source_path: Path) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)
    binary_path = build_dir / "video_ocr_interval"
    needs_build = not binary_path.exists() or source_path.stat().st_mtime > binary_path.stat().st_mtime
    if needs_build:
        proc = subprocess.run(
            ["xcrun", "swiftc", str(source_path), "-o", str(binary_path)],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "swiftc failed").strip())
    return binary_path


def run(args) -> int:
    video_path = Path(args.video).expanduser().resolve()
    out_json = Path(args.out_json).expanduser().resolve()
    build_dir = Path(args.build_dir).expanduser().resolve()
    source_path = Path(args.swift_source).expanduser().resolve() if args.swift_source else bundled_swift_source()
    binary_path = ensure_compiled_binary(build_dir, source_path)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [str(binary_path), str(video_path), str(args.interval), str(out_json)],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "video ocr failed").strip())
    if proc.stdout.strip():
        print(proc.stdout.strip())
    print(f"ocr json written to {out_json}")
    return 0
