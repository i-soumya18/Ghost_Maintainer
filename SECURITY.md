# Security Policy

## Supported Versions

We release patches and security fixes for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Threat Model & Core Invariants

The Ghost Maintainer is designed with strict security and honesty guarantees:
1. **Target Repository Isolation**: Ghost Maintainer strictly accesses repositories in **read-only mode**. It never writes, modifies, creates, or deletes files or commits inside any analyzed repository directory.
2. **Deterministic Cache Boundaries**: All BM25 indices, commit metadata stores, and query artifacts are written solely to isolated user cache directories (`~/.ghost/<repo-hash>/`).
3. **Citation Integrity Guarantee**: Every model claim in ghost voice citing historical facts must resolve to a valid commit hash verified through `git cat-file -e <hash>^{commit}` and verified against ground-truth index evidence. Any hallucinated hash or ungrounded assertion is caught by our 3-stage defense-in-depth pipeline and rejected.

## Reporting a Vulnerability

If you discover a security vulnerability or bypass in the honesty/isolation boundaries of The Ghost Maintainer, please do not open a public issue.

Instead, please send an email to:
**security@ghostmaintainer.dev**

Include:
- A description of the vulnerability (e.g. prompt injection evasion, cache directory traversal, denial-of-service vector).
- Steps to reproduce or a minimal proof-of-concept repository / query.
- The version of `ghost-maintainer` and Python environment used.

### Response Timelines
- **Initial Acknowledgement**: Within 24 hours.
- **Triage & Status Assessment**: Within 72 hours.
- **Patch Release & Public Disclosure**: Coordinated within 14 days of patch confirmation.
