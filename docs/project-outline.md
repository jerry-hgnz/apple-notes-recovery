# Apple Notes Recovery Project Outline

## Positioning

This project should be framed as an evidence-driven recovery toolkit for Apple Notes on macOS.

It is **not** a magic undelete button.
Its value is:

- taking a safe snapshot before any live mutation
- extracting evidence from multiple sources
- separating direct evidence from inference
- isolating uncertain notes into a review bucket
- generating auditable restore plans and logs

## Recommended Repository Name

The current folder name `Apple Note Recovery` is understandable, but slightly fuzzy.

Better public names:

- `Apple Notes Recovery`
- `apple-notes-recovery`
- `apple-notes-recovery-cli`

Why:

- the Apple app is named `Notes`, not `Note`
- the repository should read like a reusable tool, not a one-off action

## Core Features

- `snapshot`
  - copy `NoteStore.sqlite`, `-wal`, and `-shm`
  - export live note manifests from a chosen folder
  - export known folder names for an account

- `carve-db`
  - best-effort recovery of stale folder mappings from copied SQLite pages
  - useful when folder metadata has already been overwritten in live rows

- `video-ocr`
  - OCR a screen recording from iPad, iPhone, or QuickTime
  - emit structured frame text with geometry and confidence
  - should be treated as an optional fallback path, not the default recovery path

- `compare-video-live`
  - convert OCR output into `folder + title` observations
  - match those observations against live note titles
  - split results into exact, fuzzy, ambiguous, and unmatched buckets

- `fuse`
  - merge local DB evidence and optional fallback evidence
  - emit:
    - direct evidence assignments
    - residual bucket inference
    - review-needed notes

- `plan-restore`
  - build a single restore plan from the evidence buckets

- `restore`
  - dry-run or apply the restore plan to live Notes
  - write success and failure logs

## Recovery Problems This Tool Solves

### 1. Content vs. Folder Mapping

In many Apple Notes incidents, note content is still present in `Recently Deleted`, but the original folder metadata has been overwritten.

This creates a two-part problem:

- recover the notes themselves
- recover or reconstruct their original folder mapping

### 2. Local Database Limitations

The local database may already have overwritten:

- the current folder foreign key
- CloudKit parent references
- high-value WAL frames

So the remaining recoverable metadata may only survive in:

- stale cells
- free pages
- page gaps
- freelist remnants

This is why the carving module must be treated as best-effort forensics, not a guaranteed API.

### 3. Ambiguity in Titles

Video-based recovery is powerful, but titles alone are not always unique.

Problems include:

- duplicate titles across folders
- OCR errors
- truncated titles
- fast scrolling
- incomplete folder headers

### 4. Unsafe Recovery Behavior

The worst class of tools would treat every note as equally certain.

This project avoids that by explicitly separating:

- direct evidence
- inference
- review-needed items

## Solution Strategy

1. Freeze the scene.
2. Snapshot live data before any mutation.
3. Export live note manifests.
4. Recover direct evidence from copied local database artifacts.
5. If needed, recover more direct evidence from OCR over device recordings.
6. Fuse all evidence into confidence tiers.
7. Build a restore plan.
8. Dry-run first.
9. Apply the restore plan.
10. Put uncertain notes into a dedicated review folder instead of silently guessing.

## Why This Is Generalizable

This project is designed around reusable inputs and outputs, not a single user’s machine state.

It is generalizable because:

- all paths are passed via CLI arguments
- account name is configurable
- video runs are passed as directories instead of hardcoded names
- residual bucket logic is configurable through `--residual-folder`
- expected folder counts are optional, not required
- every stage emits TSV or JSON artifacts that can be inspected and reused

## What Is Still Best-Effort

The following are intentionally best-effort:

- `carve-db`
  - tied to Apple Notes storage schema
  - depends on surviving stale bytes

- OCR-based matching
  - depends on recording quality
  - depends on readable folder headers and titles

- residual bucket inference
  - only safe when positioned as inference, not certainty

## CLI Flow

```bash
notes-recover snapshot --out-dir ./snapshot
notes-recover carve-db --db ./snapshot/raw_live_db/NoteStore.sqlite --out-dir ./artifacts/carve
notes-recover video-ocr recovery.mov --interval 0.1 --out-json ./artifacts/ocr/frames.json
notes-recover compare-video-live --ocr-json ./artifacts/ocr/frames.json --live-titles ./snapshot/manifests/live_folder_notes.tsv --known-folders ./snapshot/manifests/folder_names.tsv --out-dir ./artifacts/video_match
notes-recover fuse --live-titles ./snapshot/manifests/live_folder_notes.tsv --folder-names ./snapshot/manifests/folder_names.tsv --mac-mappings ./artifacts/carve/recovered_restorable_mappings.tsv --video-run-dir ./artifacts/video_match --residual-folder Archive --out-dir ./artifacts/final
notes-recover plan-restore --direct ./artifacts/final/direct_evidence_assignments.tsv --residual ./artifacts/final/residual_bucket_inference.tsv --review ./artifacts/final/review_needed.tsv --review-folder "Recovery Review" --out ./artifacts/restore_plan.tsv
notes-recover restore --plan ./artifacts/restore_plan.tsv --success-log ./artifacts/restore_success.tsv --failure-log ./artifacts/restore_failure.tsv
notes-recover restore --plan ./artifacts/restore_plan.tsv --success-log ./artifacts/restore_success.tsv --failure-log ./artifacts/restore_failure.tsv --apply
```

## Next Packaging Work

- add a verification command
- add an HTML or Markdown report generator
- add installation docs for `pipx` and signed macOS permissions requirements
- add tests around:
  - text normalization
  - video matching logic
  - evidence fusion
  - restore plan generation
