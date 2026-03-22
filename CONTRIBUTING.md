# Contributing

Thanks for contributing.

## Principles

- favor safety over cleverness
- prefer evidence-driven recovery over silent guessing
- keep read-only and mutating operations clearly separated
- preserve machine-readable outputs

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Pull request expectations

- explain user impact and risk
- describe whether the change affects read-only commands, mutating commands, or both
- include tests when logic changes
- avoid hardcoded local paths
- do not add personal recovery artifacts or private note data

## Recovery safety rules

- snapshot-first behavior must remain easy to understand
- mutating commands must remain explicit
- review buckets should not be silently merged into direct evidence
