#!/usr/bin/env python3
"""Record REAL Ghost Maintainer sessions for the static replay demo.

For every curated question in a plan file this runs the actual ``Seance``
pipeline in both ``guarded`` and ``raw`` mode and stores the verbatim SSE
events (with timing) plus the slim commit payloads the web UI's drawer needs.

Honesty rule: the ``mock`` backend produces canned text, so recordings made with
it must never be published as demos. This script refuses ``mock`` unless
``--allow-mock`` is given together with an explicit ``--out`` directory (used for
UI plumbing tests only), and always stamps the backend into every recording.

Usage:
    uv run python scripts/record_replays.py --backend openai_compat --model qwen3:4b
    uv run python scripts/record_replays.py --backend mock --allow-mock --out build/replays-test
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ghost_maintainer.gitlog import ShallowCloneWarning
from ghost_maintainer.index import index_repo
from ghost_maintainer.seance import Seance

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "scripts" / "replay_plan.json"
DEFAULT_OUT = ROOT / "web" / "public" / "replays"
DIFF_LIMIT = 12_000


def slim_commit(repo: Path, commit: Any) -> dict[str, Any]:
    """Build the CommitDetails payload (mirrors server.CommitDetails) for one commit."""
    diff_text: str | None = None
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", "-p", "--stat", commit.sha],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode == 0:
        diff_text = proc.stdout
        if len(diff_text) > DIFF_LIMIT:
            diff_text = diff_text[:DIFF_LIMIT] + "\n... [diff truncated for the hosted demo]"
    return {
        "sha": commit.sha,
        "short": commit.short,
        "author": commit.author,
        "email": "",  # never ship contributor e-mail addresses in a public demo
        "date": commit.date.isoformat(),
        "subject": commit.subject,
        "body": commit.body,
        "files": [
            {"path": f.path, "added": f.added, "deleted": f.deleted, "is_binary": f.is_binary}
            for f in commit.files
        ],
        "hunks": list(commit.hunks),
        "diff": diff_text,
    }


def run_once(
    question: str, repo: Path, mode: str, backend: str, k: int
) -> tuple[list[dict[str, Any]], set[str]]:
    """Run the pipeline once; return timed verbatim events and evidence commit SHAs."""
    seance = Seance()
    start = time.monotonic()
    events: list[dict[str, Any]] = []
    evidence_shas: set[str] = set()
    for ev in seance.ask(question=question, repo_path=repo, mode=mode, backend_name=backend, k=k):
        payload = ev.to_dict()
        if ev.event == "evidence":
            for item in payload["evidence"]:
                evidence_shas.add(item["commit"]["sha"])
        events.append(
            {
                "t": int((time.monotonic() - start) * 1000),
                "event": ev.event,
                "data": json.dumps(payload),
            }
        )
    return events, evidence_shas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--backend", required=True, choices=["unsloth", "openai_compat", "mock"])
    parser.add_argument("--model", default=None, help="Model id to stamp into recordings.")
    parser.add_argument("--allow-mock", action="store_true")
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--only", default=None, help="Only record this repo id.")
    args = parser.parse_args()

    if args.backend == "mock" and (not args.allow_mock or args.out is None):
        print(
            "Refusing to record with the mock backend: its answers are canned and must not "
            "be published as a demo. Pass --allow-mock AND an explicit --out for UI tests.",
            file=sys.stderr,
        )
        return 2
    out: Path = args.out or DEFAULT_OUT
    warnings.simplefilter("ignore", ShallowCloneWarning)

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    index_path = out / "index.json"
    index: dict[str, Any] = {"version": 1, "repos": []}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))

    for repo_cfg in plan["repos"]:
        if args.only and repo_cfg["id"] != args.only:
            continue
        repo = (ROOT / repo_cfg["path"]).resolve()
        store, _, meta = index_repo(repo)
        print(f"[{repo_cfg['id']}] {len(store)} commits")
        recordings: list[dict[str, Any]] = []
        for q in repo_cfg["questions"]:
            print(f"  - {q['question']}")
            guarded, g_shas = run_once(q["question"], repo, "guarded", args.backend, args.k)
            raw, r_shas = run_once(q["question"], repo, "raw", args.backend, args.k)
            commits = {}
            for sha in sorted(g_shas | r_shas):
                found = store.get(sha)
                if found is not None:
                    commits[sha] = slim_commit(repo, found)
            rec = {
                "version": 1,
                "repo_id": repo_cfg["id"],
                "question": q["question"],
                "backend": args.backend,
                "model": args.model,
                "recorded_at": datetime.now(UTC).isoformat(),
                "commits": commits,
                "runs": {"guarded": {"events": guarded}, "raw": {"events": raw}},
            }
            rel = f"{repo_cfg['id']}/{q['id']}.json"
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            recordings.append(
                {
                    "id": q["id"],
                    "question": q["question"],
                    "trap": bool(q.get("trap", False)),
                    "file": rel,
                }
            )
        entry = {
            "id": repo_cfg["id"],
            "name": repo_cfg["name"],
            "commit_count": meta.get("commit_count", len(store)),
            "head_sha": meta.get("head_sha"),
            "recorded_at": datetime.now(UTC).isoformat(),
            "backend": args.backend,
            "model": args.model,
            "blurb": repo_cfg.get("blurb"),
            "recordings": recordings,
        }
        index["repos"] = [r for r in index["repos"] if r["id"] != entry["id"]] + [entry]

    out.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

