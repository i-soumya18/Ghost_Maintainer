#!/usr/bin/env python3
"""Verify recorded replays before they are published.

Checks, for every recording referenced by ``index.json``:

1. The recording was made by a real backend (not ``mock``) unless ``--allow-mock``.
2. Every ``[hash]`` cited in a *guarded* run's final verdict resolves to a commit
   object that really exists in the repository (``git cat-file -e <sha>^{commit}``)
   and is bundled with the recording so the web drawer can open it.
3. No contributor e-mail addresses are shipped.
4. Trap recordings end in the canonical refusal; the guarded run never keeps an
   unverified sentence.

Exit code is non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HASH_RE = re.compile(r"\[([0-9a-f]{7,40})\]", re.IGNORECASE)
REFUSAL = "The dead do not remember."


def peels_to_commit(repo: Path, sha: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def final_text(run: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Return (joined token text, verdict sentences) for a run."""
    text = ""
    sentences: list[dict[str, Any]] = []
    for ev in run["events"]:
        payload = json.loads(ev["data"])
        if ev["event"] == "token":
            text += payload.get("token", "")
        elif ev["event"] == "verdict":
            sentences = payload.get("sentences", [])
    return text, sentences


def verify_recording(rec: dict[str, Any], repo: Path | None, trap: bool) -> list[str]:
    problems: list[str] = []
    commits: dict[str, Any] = rec["commits"]
    run = rec["runs"]["guarded"]
    text, sentences = final_text(run)

    cited: set[str] = set()
    for s in sentences:
        if s.get("status") != "verified":
            problems.append(f"guarded verdict kept a non-verified sentence: {s.get('text', '')[:60]!r}")
        cited.update(m.lower() for m in HASH_RE.findall(s.get("text", "")))
    if not sentences:
        cited.update(m.lower() for m in HASH_RE.findall(text))

    for sha in sorted(cited):
        bundled = [k for k in commits if k.startswith(sha) or sha.startswith(k)]
        if not bundled:
            problems.append(f"cited [{sha}] is not bundled with the recording")
        if repo is not None and not peels_to_commit(repo, sha):
            problems.append(f"cited [{sha}] is not a real commit in the repository")

    for sha, c in commits.items():
        if c.get("email"):
            problems.append(f"commit {sha[:7]} ships an e-mail address")

    if trap and REFUSAL not in text and not any(REFUSAL in s.get("text", "") for s in sentences):
        problems.append("trap question was not refused by the guarded run")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("replay_dir", type=Path, nargs="?", default=ROOT / "web" / "public" / "replays")
    ap.add_argument("--plan", type=Path, default=ROOT / "scripts" / "replay_plan.json")
    ap.add_argument("--allow-mock", action="store_true")
    args = ap.parse_args()

    index = json.loads((args.replay_dir / "index.json").read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    repo_paths = {r["id"]: (ROOT / r["path"]).resolve() for r in plan["repos"]}

    failures = 0
    checked = 0
    for repo in index["repos"]:
        repo_path = repo_paths.get(repo["id"])
        if repo_path is not None and not repo_path.exists():
            print(f"note: {repo['id']} repository not found locally; skipping git-peel check (bundle check only)")
            repo_path = None
        for r in repo["recordings"]:
            rec = json.loads((args.replay_dir / r["file"]).read_text(encoding="utf-8"))
            problems = []
            if rec["backend"] == "mock" and not args.allow_mock:
                problems.append("recorded with the mock backend (canned output)")
            problems += verify_recording(rec, repo_path, r["trap"])
            checked += 1
            status = "FAIL" if problems else "ok  "
            print(f"{status} {repo['id']}/{r['id']}")
            for p in problems:
                print(f"       - {p}")
            failures += bool(problems)

    print(f"\n{checked} recordings checked, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
