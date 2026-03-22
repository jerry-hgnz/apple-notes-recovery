# apple-notes-recovery

Evidence-driven recovery toolkit for Apple Notes on macOS.

This project is designed for incidents where notes still exist in a live or deleted state, but their original folder mapping is incomplete, overwritten, or ambiguous.

It is **not** positioned as a guaranteed one-click undelete tool.
Instead, it provides a safer and more honest workflow:

- snapshot local state before mutation
- extract direct evidence from local artifacts
- optionally use OCR from device recordings as a fallback evidence source
- fuse evidence into direct, inferred, and review-needed buckets
- generate an auditable restore plan
- apply the plan with logs

## Repository and Package Naming

- Recommended GitHub repository name: `apple-notes-recovery`
- Python distribution name: `apple-notes-recovery`
- Python import package: `apple_notes_recovery`

The hyphenated form is correct for the repo and package name.
The underscored form is required for Python imports.

## Who This Is For

This project is for people who need a safer recovery workflow than "click around and hope."

Typical use cases:

- notes were moved into a deleted or fallback folder
- note content still exists, but original folder mapping is unclear
- local database metadata is partially overwritten
- a second device can provide fallback evidence through a recording

## What This Tool Is Not

- not a universal undelete button
- not guaranteed to recover every note perfectly
- not guaranteed to work across every future Apple Notes schema revision
- not a replacement for backups

## Scope

### Primary path

The default recovery path is local and evidence-driven:

1. snapshot the local Notes state
2. export live note metadata
3. attempt best-effort local database carving
4. build a restore plan
5. dry-run before applying

### Optional fallback path

If local database evidence is insufficient, the toolkit can use OCR from a screen recording as a **Plan B** evidence source.

Examples:

- an offline iPad showing folder lists and note titles
- a QuickTime recording of a connected device

This fallback should be documented as optional, not required.

## Installation

### Local development

```bash
git clone <your-repo-url>
cd apple-notes-recovery
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Recommended end-user install

Once published to PyPI:

```bash
pipx install apple-notes-recovery
```

## Features

- `snapshot`
  - copy `NoteStore.sqlite`, `NoteStore.sqlite-wal`, and `NoteStore.sqlite-shm`
  - export folder names for a Notes account
  - export note metadata from a chosen folder

- `carve-db`
  - best-effort recovery of stale folder mappings from a copied Notes database
  - useful when live rows already point at a fallback or deleted folder

- `video-ocr`
  - OCR a screen recording into structured frame-level text

- `compare-video-live`
  - match OCR-derived folder/title pairs against live note titles

- `fuse`
  - merge multiple evidence sources into:
    - direct evidence assignments
    - residual bucket inference
    - review-needed notes

- `plan-restore`
  - turn evidence buckets into a restore plan

- `restore`
  - dry-run or apply the restore plan
  - log success and failure rows

## Design Principles

- safety first
  - always snapshot before mutation

- evidence before inference
  - keep direct evidence separate from inferred placement

- review instead of pretending certainty
  - isolate uncertain notes in a dedicated review folder

- auditable outputs
  - every stage writes TSV or JSON artifacts

- configurable inputs
  - paths, account names, runs, and fallback folder behavior are passed through CLI arguments

## macOS Permissions

Some commands require explicit macOS permissions.

- `snapshot`
  - usually needs Full Disk Access to read the Notes group container

- `restore`
  - needs Automation permission to control `Notes.app`

- fallback workflows that use UI automation are intentionally out of scope for this repository

This tool should fail loudly when required permissions are missing.

## Current CLI

```bash
notes-recover snapshot --out-dir ./snapshot
notes-recover carve-db --db ./snapshot/raw_live_db/NoteStore.sqlite --out-dir ./artifacts/carve
notes-recover video-ocr ./recording.mov --interval 0.1 --out-json ./artifacts/ocr/frames.json
notes-recover compare-video-live --ocr-json ./artifacts/ocr/frames.json --live-titles ./snapshot/manifests/live_folder_notes.tsv --known-folders ./snapshot/manifests/folder_names.tsv --out-dir ./artifacts/video_match
notes-recover fuse --live-titles ./snapshot/manifests/live_folder_notes.tsv --folder-names ./snapshot/manifests/folder_names.tsv --mac-mappings ./artifacts/carve/recovered_restorable_mappings.tsv --video-run-dir ./artifacts/video_match --residual-folder Archive --out-dir ./artifacts/final
notes-recover plan-restore --direct ./artifacts/final/direct_evidence_assignments.tsv --residual ./artifacts/final/residual_bucket_inference.tsv --review ./artifacts/final/review_needed.tsv --review-folder "Recovery Review" --out ./artifacts/restore_plan.tsv
notes-recover restore --plan ./artifacts/restore_plan.tsv --success-log ./artifacts/restore_success.tsv --failure-log ./artifacts/restore_failure.tsv
notes-recover restore --plan ./artifacts/restore_plan.tsv --success-log ./artifacts/restore_success.tsv --failure-log ./artifacts/restore_failure.tsv --apply
```

## Core Output Artifacts

The CLI is designed around explicit, reusable artifacts:

- TSV manifests
- TSV restore plans
- TSV success and failure logs
- JSON summaries
- OCR frame JSON

This makes the tool friendlier for:

- humans
- shell pipelines
- automation
- future agent wrappers

## Agent and Automation Use

Yes, an agent *can* call this CLI, but GitHub alone is not enough.

To make that practical, the project should keep these properties:

- deterministic subcommands
- non-interactive flags
- stable exit codes
- machine-readable outputs
- clear separation between read-only commands and mutating commands

Publishing to GitHub helps discovery.
Publishing to PyPI and documenting stable CLI behavior helps actual reuse by agents and other tools.

## For Agents

This CLI is intentionally designed to be agent-friendly.

### Good properties for agent use

- non-interactive subcommands
- explicit read-only versus mutating stages
- stable file-based inputs and outputs
- TSV and JSON artifacts that are easy to parse
- dry-run support before live mutation

### Recommended calling order

```bash
notes-recover snapshot --out-dir ./snapshot
notes-recover carve-db --db ./snapshot/raw_live_db/NoteStore.sqlite --out-dir ./artifacts/carve
notes-recover fuse --live-titles ./snapshot/manifests/live_folder_notes.tsv --folder-names ./snapshot/manifests/folder_names.tsv --mac-mappings ./artifacts/carve/recovered_restorable_mappings.tsv --out-dir ./artifacts/final
notes-recover plan-restore --direct ./artifacts/final/direct_evidence_assignments.tsv --review ./artifacts/final/review_needed.tsv --out ./artifacts/restore_plan.tsv
notes-recover restore --plan ./artifacts/restore_plan.tsv --success-log ./artifacts/restore_success.tsv --failure-log ./artifacts/restore_failure.tsv
```

If local artifacts are insufficient, agents can add the optional fallback path:

```bash
notes-recover video-ocr ./recording.mov --interval 0.1 --out-json ./artifacts/ocr/frames.json
notes-recover compare-video-live --ocr-json ./artifacts/ocr/frames.json --live-titles ./snapshot/manifests/live_folder_notes.tsv --known-folders ./snapshot/manifests/folder_names.tsv --out-dir ./artifacts/video_match
notes-recover fuse --live-titles ./snapshot/manifests/live_folder_notes.tsv --folder-names ./snapshot/manifests/folder_names.tsv --mac-mappings ./artifacts/carve/recovered_restorable_mappings.tsv --video-run-dir ./artifacts/video_match --out-dir ./artifacts/final
```

### Safety expectations for agents

- treat `snapshot`, `carve-db`, `video-ocr`, `compare-video-live`, `fuse`, and `plan-restore` as read-only
- treat `restore --apply` as the only intentionally mutating step
- inspect `summary.json`, `review_needed.tsv`, and the restore plan before applying
- prefer creating a review folder for uncertain notes rather than silently guessing

### Best integration targets

- shell-based coding agents
- automation runners
- future MCP wrappers
- CI workflows for repeatable recovery analysis

## What Is Generalizable

- snapshotting Notes container state
- exporting note metadata through AppleScript
- best-effort carving from copied SQLite files
- OCR pipeline for fallback evidence
- evidence fusion logic
- restore plan generation
- dry-run and apply workflows

## What Is Not Guaranteed

- 100 percent recovery
- compatibility with all future Apple Notes schema versions
- perfect OCR on poor recordings
- unique title matching when many notes share the same title
- deterministic recovery from overwritten database pages

## Safety Model

The intended recovery order is:

1. snapshot
2. inspect artifacts
3. build evidence
4. generate a restore plan
5. dry-run
6. apply
7. verify

The repository should continue to treat `restore --apply` as the only clearly mutating step.

## Development

Run help:

```bash
PYTHONPATH=src python3 -m apple_notes_recovery --help
```

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Project Status

Current status: early alpha.

The high-level approach is validated, but the project still needs:

- more tests
- schema compatibility checks
- better error messages
- verification commands
- example datasets and fixtures
