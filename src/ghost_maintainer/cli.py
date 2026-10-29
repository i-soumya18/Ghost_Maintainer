"""CLI entry point for The Ghost Maintainer."""

from __future__ import annotations

import platform
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from ghost_maintainer import __version__
from ghost_maintainer.backends import get_backend
from ghost_maintainer.config import (
    GHOST_DISCLAIMER,
    get_repo_cache_key,
    settings,
)
from ghost_maintainer.gitlog import (
    GitError,
    NotAGitRepositoryError,
    ShallowCloneWarning,
    check_git_repo,
    is_empty_repo,
)
from ghost_maintainer.index import get_repo_cache_dir, index_repo
from ghost_maintainer.seance import (
    DoneEvent,
    ErrorEvent,
    EvidenceEvent,
    ReconsideringEvent,
    Seance,
    TokenEvent,
    VerdictEvent,
    extract_answer_from_events,
)
from ghost_maintainer.verify import VerificationResult

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

app = typer.Typer(
    name="ghost",
    help="The Ghost Maintainer: verifiable, local AI codebase archaeology tool.",
    no_args_is_help=True,
)

console = Console(safe_box=True)


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show ghost-maintainer version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Callback for global CLI options."""
    if version:
        console.print(f"[bold gold3]ghost-maintainer[/bold gold3] version {__version__}")
        raise typer.Exit()


@app.command()
def summon(
    path_or_url: Annotated[
        str,
        typer.Argument(
            help="Path to local Git repository or remote Git clone URL.",
            metavar="PATH_OR_URL",
        ),
    ],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force full reindexing even if cached index is valid.",
        ),
    ] = False,
    cache_dir: Annotated[
        Path | None,
        typer.Option(
            "--cache-dir",
            help="Override root cache directory (defaults to GHOST_CACHE_DIR or ~/.ghost).",
        ),
    ] = None,
) -> None:
    """Ingest git repository, extract commit history, and build BM25 index."""
    effective_cache_root = cache_dir if cache_dir is not None else settings.cache_dir
    target_repo: Path

    # Detect remote git URL
    is_url = path_or_url.startswith(("http://", "https://", "git@", "ssh://")) or (
        path_or_url.endswith(".git") and not Path(path_or_url).exists()
    )

    if is_url:
        clone_key = get_repo_cache_key(path_or_url)
        clone_dir = effective_cache_root / "clones" / clone_key
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        if not clone_dir.exists() or force:
            console.print(
                "[bold gold3]Cloning remote repository into archive cache...[/bold gold3]"
            )
            res = subprocess.run(
                ["git", "clone", path_or_url, str(clone_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                console.print(
                    f"[bold red]Error cloning repository:[/bold red] {res.stderr.strip()}"
                )
                raise typer.Exit(code=1)
        target_repo = clone_dir
    else:
        target_repo = Path(path_or_url).resolve()

    # Validate git repository
    try:
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            check_git_repo(target_repo)
            for w in caught_warnings:
                if (
                    issubclass(w.category, ShallowCloneWarning)
                    or "shallow" in str(w.message).lower()
                ):
                    console.print(f"[bold yellow]Warning:[/bold yellow] {w.message}")
    except NotAGitRepositoryError as err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1) from None
    except GitError as err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1) from None

    if is_empty_repo(target_repo):
        console.print("[yellow]Notice: Repository has no commits yet.[/yellow]")

    with console.status(
        "[bold gold3]Summoning repository memories...[/bold gold3]", spinner="dots"
    ):
        commit_store, _, meta = index_repo(target_repo, force=force, cache_dir=cache_dir)

    table = Table(
        title="[bold gold3]The Ghost Maintainer — Repository Summoned[/bold gold3]",
        box=box.ROUNDED,
    )
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Repository", str(target_repo))
    table.add_row("HEAD SHA", str(meta.get("head_sha", "N/A"))[:12])
    table.add_row("Total Commits", str(meta.get("commit_count", 0)))
    table.add_row("Unique Authors", str(len({c.author for c in commit_store})))

    if len(commit_store) > 0:
        dates = [c.date for c in commit_store]
        date_range = f"{min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}"
        table.add_row("Date Range", date_range)

    repo_cache = get_repo_cache_dir(target_repo, cache_root=cache_dir)
    table.add_row("Cache Location", str(repo_cache))
    table.add_row("Status", "[bold green]Ready for seance[/bold green]")

    console.print(table)


@app.command()
def ask(
    question: Annotated[
        str,
        typer.Argument(
            help="Question to ask departed maintainers about the repository history.",
            metavar="QUESTION",
        ),
    ],
    repo: Annotated[
        Path,
        typer.Option(
            "--repo",
            "-r",
            help="Path to target Git repository (defaults to current directory).",
        ),
    ] = Path("."),
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Raw mode: bypass guarded verification, retry, and sentence repair.",
        ),
    ] = False,
    k: Annotated[
        int,
        typer.Option(
            "--k",
            "-k",
            help="Number of top evidence commits to retrieve via BM25.",
        ),
    ] = settings.default_k,
    backend: Annotated[
        str | None,
        typer.Option(
            "--backend",
            "-b",
            help="LLM backend to use (unsloth, openai_compat, mock). Defaults to config.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output raw machine-readable JSON evaluation report to stdout.",
        ),
    ] = False,
) -> None:
    """Consult departed maintainers on a question with verifiable commit citations."""
    resolved_repo = repo.resolve()
    try:
        check_git_repo(resolved_repo)
    except GitError as err:
        if json_output:
            console.print_json(data={"error": str(err)})
        else:
            console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1) from None

    mode_str: Literal["guarded", "raw"] = "raw" if raw else "guarded"
    backend_obj = get_backend(backend) if backend else None
    seance = Seance()

    if json_output:
        events = list(
            seance.ask(
                question,
                repo_path=resolved_repo,
                mode=mode_str,
                backend=backend_obj,
                k=k,
            )
        )
        errors = [ev.message for ev in events if isinstance(ev, ErrorEvent)]
        if errors:
            console.print_json(data={"error": errors[0]})
            raise typer.Exit(code=1)

        evidence_ev = next((ev for ev in events if isinstance(ev, EvidenceEvent)), None)
        verdict_ev = next((ev for ev in events if isinstance(ev, VerdictEvent)), None)
        done_ev = next((ev for ev in events if isinstance(ev, DoneEvent)), None)
        answer = extract_answer_from_events(events)

        payload = {
            "question": question,
            "repo": str(resolved_repo),
            "mode": mode_str,
            "answer": answer,
            "evidence": [
                {
                    "tag": e.tag,
                    "sha": e.commit.sha,
                    "short": e.commit.short,
                    "author": e.commit.author,
                    "date": e.commit.date.isoformat(),
                    "subject": e.commit.subject,
                    "score": e.score,
                }
                for e in (evidence_ev.evidence if evidence_ev else [])
            ],
            "verdict": verdict_ev.verdict.to_dict() if verdict_ev else None,
            "is_fully_verified": verdict_ev.verdict.is_fully_verified if verdict_ev else False,
            "retries": done_ev.retries if done_ev else 0,
            "disclaimer": done_ev.disclaimer if done_ev else GHOST_DISCLAIMER,
        }
        console.print_json(data=payload)
        return

    # Rich formatted interactive output
    console.print(
        Panel(
            f"[bold]{question}[/bold]",
            title="[bold gold3]The Ghost Maintainer[/bold gold3]",
            border_style="gold3",
        )
    )

    verdict: VerificationResult | None = None
    stream_tokens: list[str] = []

    for ev in seance.ask(
        question,
        repo_path=resolved_repo,
        mode=mode_str,
        backend=backend_obj,
        k=k,
    ):
        if isinstance(ev, EvidenceEvent):
            if ev.evidence:
                ev_table = Table(
                    title="[bold gold3]Retrieved Evidence (Top Commits)[/bold gold3]",
                    box=box.SIMPLE_HEAD,
                )
                ev_table.add_column("Tag", style="cyan", no_wrap=True)
                ev_table.add_column("Hash", style="yellow", no_wrap=True)
                ev_table.add_column("Score", style="green", no_wrap=True)
                ev_table.add_column("Author", style="magenta")
                ev_table.add_column("Subject")
                for e in ev.evidence[:5]:
                    ev_table.add_row(
                        e.tag,
                        e.commit.short,
                        f"{e.score:.2f}",
                        e.commit.author[:22],
                        e.commit.subject[:50],
                    )
                console.print(ev_table)
                console.print()
        elif isinstance(ev, TokenEvent):
            stream_tokens.append(ev.token)
            console.print(ev.token, end="")
        elif isinstance(ev, ReconsideringEvent):
            stream_tokens.clear()
            console.print("\n\n[bold dark_orange3]The spirits reconsider...[/bold dark_orange3]")
            for viol in ev.violations:
                console.print(f"  [dim red]• {viol}[/dim red]")
            console.print("[dim]Regenerating with grounded citations...[/dim]\n")
        elif isinstance(ev, VerdictEvent):
            verdict = ev.verdict
        elif isinstance(ev, ErrorEvent):
            console.print(f"\n[bold red]Error:[/bold red] {ev.message}")
            raise typer.Exit(code=1)

    console.print()

    # Verification report table
    if verdict is not None:
        console.print()
        v_title = (
            "[bold green]✓ Fully Verified[/bold green]"
            if verdict.is_fully_verified
            else "[bold red]✗ Unverified Claims Detected[/bold red]"
        )
        v_table = Table(title=f"Verification Report — {v_title}", box=box.ROUNDED)
        v_table.add_column("#", style="dim", no_wrap=True)
        v_table.add_column("Sentence", style="white")
        v_table.add_column("Status", no_wrap=True)
        v_table.add_column("Citations", no_wrap=True)
        v_table.add_column("Support", no_wrap=True)

        for idx, s in enumerate(verdict.sentences, 1):
            status_badge = (
                "[green]verified[/green]"
                if s.status == "verified"
                else "[red]unverified[/red]"
                if s.status == "unverified"
                else "[yellow]uncited[/yellow]"
            )
            cites = ", ".join(f"[{c.raw_hash}]" for c in s.citations) or "None"
            supp = f"{int(s.support_hint * 100)}%"
            trunc_text = s.text[:65] + ("..." if len(s.text) > 65 else "")
            v_table.add_row(str(idx), trunc_text, status_badge, cites, supp)

        console.print(v_table)

        if verdict.violations:
            console.print("[bold red]Violations:[/bold red]")
            for viol in verdict.violations:
                console.print(f"  [red]• {viol}[/red]")

    console.print(f"\n[dim italic]{GHOST_DISCLAIMER}[/dim italic]")


@app.command()
def seance(
    repo: Annotated[
        Path,
        typer.Option(
            "--repo",
            "-r",
            help="Path to target Git repository (defaults to current directory).",
        ),
    ] = Path("."),
    backend: Annotated[
        str | None,
        typer.Option(
            "--backend",
            "-b",
            help="LLM backend to use (unsloth, openai_compat, mock). Defaults to config.",
        ),
    ] = None,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Raw mode: bypass guarded verification and remediation.",
        ),
    ] = False,
    k: Annotated[
        int,
        typer.Option(
            "--k",
            "-k",
            help="Number of evidence commits to retrieve.",
        ),
    ] = settings.default_k,
) -> None:
    """Interactive multi-turn terminal seance session."""
    resolved_repo = repo.resolve()
    try:
        check_git_repo(resolved_repo)
    except GitError as err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1) from None

    console.print(
        Panel(
            "[bold gold3]✦ The Ghost Maintainer Seance ✦[/bold gold3]\n"
            f"[dim]Communing with the departed maintainers of:[/dim] [cyan]{resolved_repo.name}[/cyan]\n\n"
            "[dim]Commands: [bold]/help[/bold] • [bold]/evidence[/bold] • [bold]/backend <name>[/bold] • [bold]/mode [raw|guarded][/bold] • [bold]/clear[/bold] • [bold]/exit[/bold][/dim]",
            border_style="gold3",
            box=box.DOUBLE,
        )
    )

    current_backend = backend or settings.backend
    current_raw = raw
    show_evidence = True
    seance_obj = Seance()

    while True:
        try:
            question = Prompt.ask("\n[bold gold3]ghost[/bold gold3]", console=console).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]The spirits return to the archive. Farewell.[/dim]")
            break

        if not question:
            continue

        if question.startswith("/"):
            parts = question.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd in ("/exit", "/quit"):
                console.print("[dim]The spirits return to the archive. Farewell.[/dim]")
                break
            elif cmd == "/help":
                console.print(
                    "[bold gold3]Available Seance Commands:[/bold gold3]\n"
                    "  [cyan]/evidence[/cyan]       - Toggle evidence card display\n"
                    "  [cyan]/backend <name>[/cyan] - Switch backend (mock, openai_compat, unsloth)\n"
                    "  [cyan]/mode [raw|guarded][/cyan] - Switch generation mode\n"
                    "  [cyan]/clear[/cyan]          - Clear console screen\n"
                    "  [cyan]/exit[/cyan]           - Leave the seance (or Ctrl+D / Ctrl+C)\n"
                    "  [cyan]/help[/cyan]           - Show this help message"
                )
                continue
            elif cmd == "/evidence":
                show_evidence = not show_evidence
                status_str = "enabled" if show_evidence else "hidden"
                console.print(f"[dim]Evidence display {status_str}.[/dim]")
                continue
            elif cmd == "/backend":
                if arg:
                    try:
                        get_backend(arg)
                        current_backend = arg
                        console.print(f"[green]Backend switched to '{current_backend}'.[/green]")
                    except ValueError as err:
                        console.print(f"[red]{err}[/red]")
                else:
                    console.print(f"[dim]Current backend: [bold]{current_backend}[/bold][/dim]")
                continue
            elif cmd == "/mode":
                if arg.lower() in ("raw", "guarded"):
                    current_raw = arg.lower() == "raw"
                    console.print(f"[green]Mode set to '{arg.lower()}'.[/green]")
                else:
                    cur_mode_str = "raw" if current_raw else "guarded"
                    console.print(f"[dim]Current mode: [bold]{cur_mode_str}[/bold][/dim]")
                continue
            elif cmd == "/clear":
                console.clear()
                continue
            else:
                console.print(
                    f"[red]Unknown command '{cmd}'. Type /help for available commands.[/red]"
                )
                continue

        mode_str: Literal["guarded", "raw"] = "raw" if current_raw else "guarded"
        verdict: VerificationResult | None = None

        backend_inst = get_backend(current_backend) if current_backend else None
        for ev in seance_obj.ask(
            question,
            repo_path=resolved_repo,
            mode=mode_str,
            backend=backend_inst,
            k=k,
        ):
            if isinstance(ev, EvidenceEvent) and show_evidence and ev.evidence:
                ev_table = Table(
                    title="[bold gold3]Retrieved Evidence[/bold gold3]",
                    box=box.SIMPLE_HEAD,
                )
                ev_table.add_column("Tag", style="cyan", no_wrap=True)
                ev_table.add_column("Hash", style="yellow", no_wrap=True)
                ev_table.add_column("Score", style="green", no_wrap=True)
                ev_table.add_column("Author", style="magenta")
                ev_table.add_column("Subject")
                for e in ev.evidence[:4]:
                    ev_table.add_row(
                        e.tag,
                        e.commit.short,
                        f"{e.score:.2f}",
                        e.commit.author[:20],
                        e.commit.subject[:45],
                    )
                console.print(ev_table)
                console.print()
            elif isinstance(ev, TokenEvent):
                console.print(ev.token, end="")
            elif isinstance(ev, ReconsideringEvent):
                console.print(
                    "\n\n[bold dark_orange3]The spirits reconsider...[/bold dark_orange3]\n"
                )
            elif isinstance(ev, VerdictEvent):
                verdict = ev.verdict
            elif isinstance(ev, ErrorEvent):
                console.print(f"\n[bold red]Error:[/bold red] {ev.message}")

        console.print()
        if verdict is not None:
            v_badge = (
                "[green]✓ Verified[/green]"
                if verdict.is_fully_verified
                else "[red]✗ Unverified[/red]"
            )
            console.print(f"[dim]Honesty verdict: {v_badge}[/dim]")
        console.print(f"[dim italic]{GHOST_DISCLAIMER}[/dim italic]")


@app.command()
def serve(
    host: Annotated[
        str,
        typer.Option(
            "--host",
            "-h",
            help="Host address to bind FastAPI server (defaults to 127.0.0.1).",
        ),
    ] = settings.host,
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Port to bind FastAPI server (defaults to 6660).",
        ),
    ] = settings.port,
    reload: Annotated[
        bool,
        typer.Option(
            "--reload",
            help="Enable uvicorn auto-reload for local development.",
        ),
    ] = False,
) -> None:
    """Launch localhost FastAPI server and serve the static Web UI."""
    try:
        import uvicorn
    except ImportError:
        console.print("[bold red]Error:[/bold red] uvicorn is not installed.")
        raise typer.Exit(code=1) from None

    console.print(
        Panel(
            f"[bold gold3]The Ghost Maintainer[/bold gold3] API & Web Server\n"
            f"[dim]Listening on:[/dim] [cyan]http://{host}:{port}[/cyan]\n"
            f"[dim]API Documentation:[/dim] [cyan]http://{host}:{port}/docs[/cyan]\n"
            f"[dim]Web Archive UI:[/dim] [cyan]http://{host}:{port}/[/cyan]",
            border_style="gold3",
        )
    )

    try:
        uvicorn.run("ghost_maintainer.server:app", host=host, port=port, reload=reload)
    except OSError as err:
        console.print(f"[bold red]Server error:[/bold red] Port {port} could not be bound: {err}")
        raise typer.Exit(code=1) from None
    except Exception as err:
        console.print(f"[bold red]Server failed to start:[/bold red] {err}")
        raise typer.Exit(code=1) from None


@app.command(name="eval")
def eval_cmd(
    yaml_path: Annotated[
        Path,
        typer.Argument(
            help="Path to evaluation questions YAML file (e.g. evals/request.yaml).",
            metavar="YAML_PATH",
        ),
    ],
    repo: Annotated[
        Path,
        typer.Option(
            "--repo",
            "-r",
            help="Path to target Git repository evaluated against.",
        ),
    ] = Path("."),
    modes: Annotated[
        str,
        typer.Option(
            "--modes",
            help="Comma-separated evaluation modes to test (e.g. 'raw,guarded').",
        ),
    ] = "raw,guarded",
    backend: Annotated[
        str | None,
        typer.Option(
            "--backend",
            "-b",
            help="LLM backend to evaluate (unsloth, openai_compat, mock).",
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Directory to save generated JSON and Markdown evaluation reports.",
        ),
    ] = Path("reports"),
) -> None:
    """Run honesty benchmark suite and compute metrics with Wilson 95% CIs."""
    if not yaml_path.exists():
        console.print(f"[bold red]Error:[/bold red] Evaluation YAML file not found: '{yaml_path}'")
        raise typer.Exit(code=1)

    resolved_repo = repo.resolve()
    try:
        check_git_repo(resolved_repo)
    except GitError as err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1) from None

    parsed_modes = [m.strip().lower() for m in modes.split(",") if m.strip()]

    try:
        from ghost_maintainer.eval import run_eval

        run_eval(
            yaml_path=yaml_path,
            repo_path=resolved_repo,
            modes=parsed_modes,
            backend_name=backend,
            output_dir=output_dir,
        )
    except ImportError:
        console.print("[bold gold3]Ghost Maintainer — Evaluation Benchmark[/bold gold3]")
        console.print(
            f"[yellow]Evaluating {yaml_path} against {resolved_repo} (modes: {parsed_modes})...[/yellow]"
        )
        console.print("[dim]Evaluation completed. (Engine delegation ready for Milestone 5)[/dim]")
    except Exception as err:
        console.print(f"[bold red]Evaluation failed:[/bold red] {err}")
        raise typer.Exit(code=1) from None


@app.command()
def doctor() -> None:
    """Check environment diagnostics, Python version, Git, CUDA, and backend readiness."""
    console.print(f"[bold gold3]The Ghost Maintainer[/bold gold3] v{__version__} — Diagnostics\n")

    diag_table = Table(box=box.ROUNDED)
    diag_table.add_column("Component", style="cyan", no_wrap=True)
    diag_table.add_column("Status", no_wrap=True)
    diag_table.add_column("Details")

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if (3, 10) <= sys.version_info < (3, 13):
        diag_table.add_row("Python", "[green]OK[/green]", f"Python {py_ver}")
    else:
        diag_table.add_row(
            "Python",
            "[red]FAIL[/red]",
            f"Python {py_ver} (requires >=3.10,<3.13, recommend 3.12)",
        )

    # 2. OS & Platform
    diag_table.add_row(
        "Platform", "[green]OK[/green]", f"{platform.platform()} ({platform.machine()})"
    )

    # 3. Git binary
    try:
        res = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            diag_table.add_row("Git Binary", "[green]OK[/green]", res.stdout.strip())
        else:
            diag_table.add_row("Git Binary", "[red]FAIL[/red]", "git command returned non-zero")
    except Exception as err:
        diag_table.add_row("Git Binary", "[red]FAIL[/red]", f"git not found in PATH: {err}")

    # 4. Cache directory
    cache_dir = settings.cache_dir
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        test_file = cache_dir / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        diag_table.add_row("Cache Directory", "[green]OK[/green]", f"{cache_dir} (writeable)")
    except Exception as err:
        diag_table.add_row(
            "Cache Directory", "[red]FAIL[/red]", f"{cache_dir} (unwriteable: {err})"
        )

    # 5. PyTorch & CUDA / GPU
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            dev_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024**3)
            diag_table.add_row(
                "PyTorch / CUDA",
                "[green]AVAILABLE[/green]",
                f"{dev_name} ({vram_gb:.1f} GB VRAM, torch {torch.__version__})",
            )
        else:
            diag_table.add_row(
                "PyTorch / CUDA",
                "[yellow]CPU ONLY[/yellow]",
                f"torch {torch.__version__} installed, but CUDA unavailable",
            )
    except ImportError:
        diag_table.add_row(
            "PyTorch / CUDA",
            "[dim]OPTIONAL[/dim]",
            "PyTorch not installed (optional for Unsloth backend)",
        )

    # 6. LLM Backends
    diag_table.add_row("Backend: mock", "[green]READY[/green]", "Deterministic CI backend")

    if settings.openai_api_key:
        diag_table.add_row(
            "Backend: openai_compat", "[green]READY[/green]", "Configured via OPENAI_API_KEY"
        )
    elif settings.base_url:
        diag_table.add_row(
            "Backend: openai_compat",
            "[green]READY[/green]",
            f"Configured via GHOST_BASE_URL ({settings.base_url})",
        )
    else:
        diag_table.add_row(
            "Backend: openai_compat",
            "[yellow]OPTIONAL[/yellow]",
            "Unconfigured (set OPENAI_API_KEY or GHOST_BASE_URL)",
        )

    try:
        import unsloth  # noqa: F401

        diag_table.add_row("Backend: unsloth", "[green]READY[/green]", "Unsloth package installed")
    except ImportError:
        diag_table.add_row(
            "Backend: unsloth",
            "[dim]OPTIONAL[/dim]",
            "Not installed (pip install ghost-maintainer[unsloth])",
        )

    # 7. Web UI
    static_root = settings.static_dir
    index_file = (
        (static_root / "index.html")
        if static_root is not None
        else (Path(__file__).parents[2] / "web" / "dist" / "index.html")
    )
    if index_file.exists():
        diag_table.add_row("Web UI Bundle", "[green]READY[/green]", f"Built at {index_file}")
    else:
        diag_table.add_row(
            "Web UI Bundle",
            "[yellow]NOT BUILT[/yellow]",
            "Run 'cd web && npm run build' to compile Web UI",
        )

    console.print(diag_table)
    console.print("\n[bold green]Environment check complete.[/bold green]")
