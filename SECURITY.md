# Security Policy

## Scope

This project handles local note metadata, recovery artifacts, and restore plans.
It should be treated as privacy-sensitive software.

## Reporting

If you discover a security issue, privacy leak, or unsafe recovery behavior, please report it privately before opening a public issue.

Recommended categories:

- unintended data disclosure
- destructive behavior without explicit apply step
- incorrect restore plan generation that can silently misplace notes
- shell injection or path traversal issues

## Safe defaults

- read-only steps should be non-mutating
- restore must require an explicit apply step
- outputs should avoid collecting more user content than necessary
