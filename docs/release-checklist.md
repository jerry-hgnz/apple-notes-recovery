# Release Checklist

## Naming and metadata

- confirm GitHub repo name is `apple-notes-recovery`
- confirm package name is `apple-notes-recovery`
- set final repository URLs in package metadata if you want them published
- confirm license choice

## Privacy and safety

- scan for local absolute paths
- scan for real user data, note titles, or recordings
- confirm examples use synthetic data only
- confirm `restore --apply` is the only clearly mutating command

## Documentation

- README matches actual CLI behavior
- installation instructions are correct
- permissions section is accurate
- fallback video path is documented as optional
- limitations are explicit

## Packaging

- `python3 -m unittest discover -s tests` passes
- `PYTHONPATH=src python3 -m apple_notes_recovery --help` works
- `pip install -e .` works in a clean venv
- package data includes the Swift OCR helper

## GitHub readiness

- add repository description
- add topics such as `macos`, `apple-notes`, `recovery`, `ocr`, `cli`
- enable Issues
- add a basic CI workflow

## First public release

- tag `v0.1.0`
- publish a short release note explaining:
  - what the tool does
  - what it does not guarantee
  - what is considered experimental

## Promotion prep

- prepare one short demo video or GIF
- prepare one architecture image or flow chart
- prepare one short post for GitHub, X, and developer communities
