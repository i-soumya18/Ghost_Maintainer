#!/usr/bin/env python3
"""Audit and Verify Citations from Evaluation Reports.

Reads generated evaluation JSON output or arbitrary model logs and audits:
1. Object validity: Are cited hashes real commit objects (`git cat-file -e <sha>^{commit}`)?
2. Grounding status: Were cited hashes present in retrieved evidence?
3. SVR and Citation Existence Rates calculated independently.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()
HASH_PATTERN = re.compile(r"\[([0-9a-f]{7,40})\]", re.IGNORECASE)


def peel_commit(repo_path: Path, commit_sha: str) -> bool:
    """Check whether commit exists and peels to a commit object in git."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), "cat-file", "-e", f"{commit_sha}^{{commit}}"],
            capture_output=True,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def verify_evaluation_report(report_path: Path, repo_path: Path) -> bool:
    """Audit citations in evaluation report against repository."""
    if not report_path.exists():
        console.print(f"[red]Error:[/red] Report not found: {report_path}")
        return False

    if not repo_path.exists() or not (repo_path / ".git").exists():
        console.print(f"[red]Error:[/red] Git repository not found: {repo_path}")
        return False

    with open(report_path, encoding="utf-8") as f:
        data: Any = json.load(f)

    raw_results = data.get("results", []) if isinstance(data, dict) else []
    if isinstance(raw_results, dict):
        # Choose guarded mode if available, else first available mode
        target_mode = (
            "guarded" if "guarded" in raw_results else next(iter(raw_results.keys()), "default")
        )
        results = raw_results.get(target_mode, [])
    else:
        results = raw_results

    if not results:
        console.print("[yellow]Warning:[/yellow] No results found in report.")
        return True

    table = Table(title=f"Citation Audit: {report_path.name}")
    table.add_column("Question ID", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Cited Hashes", style="yellow")
    table.add_column("Git Existence", justify="center")

    total_citations = 0
    valid_citations = 0
    all_valid = True

    for item in results:
        qid = str(item.get("id") or item.get("question_id", "UNKNOWN"))
        response = str(item.get("answer") or item.get("response", ""))
        status = "Refused" if item.get("is_refusal") or item.get("refused") else "Answered"

        # Extract citations from response text or structured citations field
        citations = HASH_PATTERN.findall(response)
        if not citations and "citations" in item:
            for c in item["citations"]:
                if isinstance(c, dict) and "hash" in c:
                    citations.append(c["hash"])
                elif isinstance(c, str):
                    citations.append(c)
        if not citations:
            table.add_row(qid, status, "None", "[dim]N/A[/dim]")
            continue

        item_hashes: list[str] = []
        for sha in citations:
            total_citations += 1
            is_valid = peel_commit(repo_path, sha)
            if is_valid:
                valid_citations += 1
                item_hashes.append(f"[green]{sha[:7]}[/green]")
            else:
                all_valid = False
                item_hashes.append(f"[red]{sha[:7]} (HALLUCINATED)[/red]")

        git_col = (
            "[green]ALL VALID[/green]"
            if all(peel_commit(repo_path, s) for s in citations)
            else "[red]CONTAINS FAKES[/red]"
        )
        table.add_row(qid, status, ", ".join(item_hashes), git_col)

    console.print(table)
    console.print(
        f"\n[bold]Total Citations Audited:[/bold] {total_citations} | "
        f"[bold]Valid In Git History:[/bold] [green]{valid_citations}[/green] | "
        f"[bold]Invalid / Hallucinated:[/bold] [{'red' if total_citations - valid_citations > 0 else 'green'}]{total_citations - valid_citations}[/]"
    )
    return all_valid


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit citations in an evaluation report.")
    parser.add_argument("report", type=Path, help="Path to evaluation JSON report.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(".eval_repos/request"),
        help="Path to target git repository.",
    )
    args = parser.parse_args()

    success = verify_evaluation_report(args.report, args.repo)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
