#!/usr/bin/env python3
"""Validate Gold Commits in Evaluation YAML.

Confirms that every gold commit hash cited in the evaluation dataset exists in
the target repository and peels cleanly to a genuine git commit object
(`git cat-file -e <sha>^{commit}`).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

console = Console()


def peel_commit(repo_path: Path, commit_sha: str) -> bool:
    """Check if commit exists in git repository using git cat-file -e <sha>^{commit}."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), "cat-file", "-e", f"{commit_sha}^{{commit}}"],
            capture_output=True,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def validate_eval_yaml(yaml_path: Path, repo_path: Path) -> bool:
    """Validate all questions and gold commit references in YAML."""
    if not yaml_path.exists():
        console.print(f"[red]Error:[/red] Evaluation file not found: {yaml_path}")
        return False

    if not repo_path.exists() or not (repo_path / ".git").exists():
        console.print(f"[red]Error:[/red] Target repository not found: {repo_path}")
        return False

    try:
        with open(yaml_path, encoding="utf-8") as f:
            data: Any = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        console.print(f"[red]Error:[/red] Invalid YAML syntax in {yaml_path}: {exc}")
        return False

    questions = data.get("questions", []) if isinstance(data, dict) else data
    if not questions:
        console.print("[red]Error:[/red] No questions found in YAML file.")
        return False

    table = Table(title=f"Evaluation Gold Commit Validation: {yaml_path.name}")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta")
    table.add_column("Question", style="white", max_width=45)
    table.add_column("Gold Commits", style="yellow")
    table.add_column("Status", justify="center")

    total_valid = 0
    total_checked = 0
    all_ok = True

    for q in questions:
        qid = q.get("id", "UNKNOWN")
        text = q.get("question") or q.get("q", "")
        answerable = q.get("answerable", True)
        raw_gold = q.get("gold_commits") or q.get("gold") or []
        if isinstance(raw_gold, str):
            gold_commits = [raw_gold.strip()] if raw_gold.strip() else []
        elif isinstance(raw_gold, list):
            gold_commits = [str(g).strip() for g in raw_gold if str(g).strip()]
        else:
            gold_commits = []

        if not answerable:
            # Trap question: should have no gold commits and expected_refusal == True
            if gold_commits:
                table.add_row(
                    qid, "Trap", text, str(gold_commits), "[red]FAIL (has gold commits)[/red]"
                )
                all_ok = False
            else:
                table.add_row(qid, "Trap", text, "-", "[green]OK (Refusal Expected)[/green]")
            continue

        # Answerable question
        if not gold_commits:
            table.add_row(qid, "Answerable", text, "None", "[red]FAIL (Missing gold commits)[/red]")
            all_ok = False
            continue

        verified_commits: list[str] = []
        item_ok = True
        for sha in gold_commits:
            total_checked += 1
            if peel_commit(repo_path, sha):
                verified_commits.append(f"[green]{sha[:7]}[/green]")
                total_valid += 1
            else:
                verified_commits.append(f"[red]{sha[:7]} (MISSING)[/red]")
                item_ok = False
                all_ok = False

        status = "[green]VALID[/green]" if item_ok else "[red]INVALID[/red]"
        table.add_row(qid, "Answerable", text, ", ".join(verified_commits), status)

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] {total_valid}/{total_checked} gold commit references verified in target repo."
    )
    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate gold commit hashes in evaluation YAML.")
    parser.add_argument(
        "--yaml",
        "-y",
        "--eval-file",
        "-e",
        dest="yaml",
        type=Path,
        default=Path("evals/request.yaml"),
        help="Path to evaluation YAML benchmark.",
    )
    parser.add_argument(
        "--repo",
        "-r",
        type=Path,
        default=Path(".eval_repos/request"),
        help="Path to target git repository.",
    )

    args = parser.parse_args()
    success = validate_eval_yaml(args.yaml, args.repo)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
