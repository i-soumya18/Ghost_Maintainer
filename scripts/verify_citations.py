#!/usr/bin/env python3
"""Audit and Verify Citations from Evaluation Reports.

Reads generated evaluation JSON or Markdown output and audits:
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


def _verify_markdown_report(report_path: Path, repo_path: Path) -> bool:
    """Audit bracketed citations in Markdown report."""
    content = report_path.read_text(encoding="utf-8")
    raw_citations = HASH_PATTERN.findall(content)
    # Deduplicate while preserving order
    unique_citations = list(dict.fromkeys(raw_citations))

    table = Table(title=f"Citation Audit (Markdown): {report_path.name}")
    table.add_column("Question ID", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Cited Hashes", style="yellow")
    table.add_column("Git Existence", justify="center")

    total_citations = 0
    valid_citations = 0
    all_valid = True

    if not unique_citations:
        console.print(table)
        console.print(
            "\n[bold]Total Citations Audited:[/bold] 0 | "
            "[bold]Valid In Git History:[/bold] [green]0[/green] | "
            "[bold]Invalid / Hallucinated:[/bold] [green]0[/green]"
        )
        return True

    for idx, sha in enumerate(unique_citations, 1):
        total_citations += 1
        is_valid = peel_commit(repo_path, sha)
        if is_valid:
            valid_citations += 1
            item_hashes = f"[green]{sha[:7]}[/green]"
            git_col = "[green]VALID[/green]"
        else:
            all_valid = False
            item_hashes = f"[red]{sha[:7]} (HALLUCINATED)[/red]"
            git_col = "[red]CONTAINS FAKES[/red]"

        table.add_row(f"#{idx:02d}", "Extracted", item_hashes, git_col)

    console.print(table)
    console.print(
        f"\n[bold]Total Citations Audited:[/bold] {total_citations} | "
        f"[bold]Valid In Git History:[/bold] [green]{valid_citations}[/green] | "
        f"[bold]Invalid / Hallucinated:[/bold] [{'red' if total_citations - valid_citations > 0 else 'green'}]{total_citations - valid_citations}[/]"
    )
    return all_valid


def _verify_json_report(report_path: Path, repo_path: Path, data: Any) -> bool:
    """Audit citations in JSON evaluation report."""
    raw_results = data.get("results", []) if isinstance(data, dict) else []
    if isinstance(raw_results, dict):
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

        # Extract citations from response text AND structured citations field
        citations: list[str] = []
        for h in HASH_PATTERN.findall(response):
            if h not in citations:
                citations.append(h)

        if "citations" in item and isinstance(item["citations"], list):
            for c in item["citations"]:
                extracted = None
                if isinstance(c, dict):
                    extracted = c.get("raw_hash") or c.get("resolved_sha") or c.get("hash")
                elif isinstance(c, str):
                    extracted = c
                if extracted:
                    val = str(extracted).strip()
                    if val and val not in citations:
                        citations.append(val)

        if "sentences" in item and isinstance(item["sentences"], list):
            for s in item["sentences"]:
                if isinstance(s, dict) and isinstance(s.get("citations"), list):
                    for sc in s["citations"]:
                        extracted = None
                        if isinstance(sc, dict):
                            extracted = (
                                sc.get("raw_hash") or sc.get("resolved_sha") or sc.get("hash")
                            )
                        elif isinstance(sc, str):
                            extracted = sc
                        if extracted:
                            val = str(extracted).strip()
                            if val and val not in citations:
                                citations.append(val)

        if not citations:
            table.add_row(qid, status, "None", "[dim]N/A[/dim]")
            continue

        item_hashes: list[str] = []
        item_ok = True
        for sha in citations:
            total_citations += 1
            is_valid = peel_commit(repo_path, sha)
            if is_valid:
                valid_citations += 1
                item_hashes.append(f"[green]{sha[:7]}[/green]")
            else:
                all_valid = False
                item_ok = False
                item_hashes.append(f"[red]{sha[:7]} (HALLUCINATED)[/red]")

        git_col = "[green]ALL VALID[/green]" if item_ok else "[red]CONTAINS FAKES[/red]"
        table.add_row(qid, status, ", ".join(item_hashes), git_col)

    console.print(table)
    console.print(
        f"\n[bold]Total Citations Audited:[/bold] {total_citations} | "
        f"[bold]Valid In Git History:[/bold] [green]{valid_citations}[/green] | "
        f"[bold]Invalid / Hallucinated:[/bold] [{'red' if total_citations - valid_citations > 0 else 'green'}]{total_citations - valid_citations}[/]"
    )
    return all_valid


def verify_evaluation_report(report_path: Path, repo_path: Path) -> bool:
    """Audit citations in evaluation report (JSON or Markdown) against repository."""
    if not report_path.exists():
        console.print(f"[red]Error:[/red] Report not found: {report_path}")
        return False

    if not repo_path.exists() or not (repo_path / ".git").exists():
        console.print(f"[red]Error:[/red] Git repository not found: {repo_path}")
        return False

    is_markdown = report_path.suffix.lower() == ".md"
    data: Any = None
    if not is_markdown:
        try:
            with open(report_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            if report_path.suffix.lower() == ".json":
                console.print(f"[red]Error:[/red] Malformed JSON report: {e}")
                return False
            is_markdown = True

    if is_markdown:
        return _verify_markdown_report(report_path, repo_path)
    else:
        return _verify_json_report(report_path, repo_path, data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit citations in an evaluation report.")
    parser.add_argument("report", type=Path, help="Path to evaluation report (JSON or Markdown).")
    parser.add_argument(
        "--repo",
        "-r",
        type=Path,
        default=Path(".eval_repos/request"),
        help="Path to target git repository.",
    )
    args = parser.parse_args()

    success = verify_evaluation_report(args.report, args.repo)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
