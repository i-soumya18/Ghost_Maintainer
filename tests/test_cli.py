"""Comprehensive hermetic tests for Typer/Rich CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ghost_maintainer import __version__
from ghost_maintainer.cli import app
from ghost_maintainer.index import index_repo

runner = CliRunner()


def test_cli_version() -> None:
    """CLI --version and -v display version string and exit cleanly."""
    res1 = runner.invoke(app, ["--version"])
    assert res1.exit_code == 0
    assert __version__ in res1.stdout

    res2 = runner.invoke(app, ["-v"])
    assert res2.exit_code == 0
    assert __version__ in res2.stdout


def test_cli_no_args_shows_help() -> None:
    """Running ghost without arguments displays help message."""
    res = runner.invoke(app, [])
    assert res.exit_code in (0, 2)
    assert "Usage" in res.stdout or "ghost" in res.stdout


def test_cli_doctor() -> None:
    """CLI doctor command prints complete diagnostics table."""
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "Diagnostics" in res.stdout
    assert "Python" in res.stdout
    assert "Git Binary" in res.stdout
    assert "Cache Directory" in res.stdout
    assert "mock" in res.stdout


def test_cli_doctor_torch_cuda_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI doctor cleanly reports CUDA availability when PyTorch is mocked."""
    import sys
    from types import ModuleType

    fake_torch = ModuleType("torch")
    fake_torch.__version__ = "2.3.0"
    fake_cuda = ModuleType("cuda")
    fake_cuda.is_available = lambda: True  # type: ignore[attr-defined]
    fake_cuda.get_device_name = lambda _idx: "NVIDIA RTX 4090"  # type: ignore[attr-defined]

    class FakeProps:
        total_memory = 24 * 1024**3

    fake_cuda.get_device_properties = lambda _idx: FakeProps()  # type: ignore[attr-defined]
    fake_torch.cuda = fake_cuda  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "RTX 4090" in res.stdout


def test_cli_summon_success(synthetic_repo: Path, tmp_path: Path) -> None:
    """CLI summon indexes synthetic repository and prints summary table."""
    res = runner.invoke(app, ["summon", str(synthetic_repo), "--cache-dir", str(tmp_path)])
    assert res.exit_code == 0
    assert "Repository Summoned" in res.stdout
    assert "Total Commits" in res.stdout
    assert "Ready for seance" in res.stdout


def test_cli_summon_force(synthetic_repo: Path, tmp_path: Path) -> None:
    """CLI summon with --force successfully rebuilds the index."""
    res1 = runner.invoke(app, ["summon", str(synthetic_repo), "--cache-dir", str(tmp_path)])
    assert res1.exit_code == 0

    res2 = runner.invoke(
        app, ["summon", str(synthetic_repo), "--cache-dir", str(tmp_path), "--force"]
    )
    assert res2.exit_code == 0
    assert "Ready for seance" in res2.stdout


def test_cli_summon_non_git(non_git_dir: Path, tmp_path: Path) -> None:
    """CLI summon fails cleanly on non-git directory with exit code 1."""
    res = runner.invoke(app, ["summon", str(non_git_dir), "--cache-dir", str(tmp_path)])
    assert res.exit_code == 1
    assert "Error:" in res.stdout


def test_cli_summon_shallow(shallow_repo: Path, tmp_path: Path) -> None:
    """CLI summon warns on shallow clone with exact required warning string."""
    res = runner.invoke(app, ["summon", str(shallow_repo), "--cache-dir", str(tmp_path)])
    assert res.exit_code == 0
    assert "History is shallow; the dead remember less." in res.stdout


def test_cli_summon_remote_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI summon detects remote git URL and initiates isolated clone."""
    import subprocess
    from datetime import UTC, datetime

    from ghost_maintainer.gitlog import Commit
    from ghost_maintainer.index import CommitStore

    called_clone = False

    def mock_subprocess_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal called_clone
        if cmd[:2] == ["git", "clone"]:
            called_clone = True
            dest = Path(cmd[3])
            dest.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="main\n", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
    monkeypatch.setattr("ghost_maintainer.cli.check_git_repo", lambda _: None)
    monkeypatch.setattr("ghost_maintainer.cli.is_empty_repo", lambda _: False)

    dummy_commit = Commit(
        sha="a" * 40,
        short="a" * 7,
        author="Tester",
        email="t@example.com",
        date=datetime.now(UTC),
        subject="init",
        body="",
        files=(),
    )
    monkeypatch.setattr(
        "ghost_maintainer.cli.index_repo",
        lambda *_, **__: (
            CommitStore([dummy_commit]),
            None,
            {"commit_count": 1, "head_sha": "a" * 40},
        ),
    )

    res = runner.invoke(
        app,
        ["summon", "https://github.com/example/repo.git", "--cache-dir", str(tmp_path)],
    )
    assert res.exit_code == 0
    assert called_clone is True


def test_cli_ask_json_verified(synthetic_repo: Path, tmp_path: Path) -> None:
    """CLI ask with --json emits machine-readable evaluation record."""
    index_repo(synthetic_repo, cache_dir=tmp_path)
    res = runner.invoke(
        app,
        [
            "ask",
            "Why was request deprecated?",
            "--repo",
            str(synthetic_repo),
            "--backend",
            "mock",
            "--json",
        ],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["question"] == "Why was request deprecated?"
    assert data["is_fully_verified"] is True
    assert len(data["evidence"]) > 0
    assert data["disclaimer"] == "Voices are fiction. Evidence is real."


def test_cli_ask_terminal_verified(synthetic_repo: Path) -> None:
    """CLI ask formatted output displays Evidence table, tokens, and Verification table."""
    res = runner.invoke(
        app,
        [
            "ask",
            "Why was request deprecated?",
            "--repo",
            str(synthetic_repo),
            "--backend",
            "mock",
        ],
    )
    assert res.exit_code == 0
    assert "Retrieved Evidence" in res.stdout
    assert "Verification Report" in res.stdout
    assert "Fully Verified" in res.stdout
    assert "Voices are fiction. Evidence is real." in res.stdout


def test_cli_ask_refusal(synthetic_repo: Path) -> None:
    """CLI ask on unanswerable query emits refusal string."""
    res = runner.invoke(
        app,
        [
            "ask",
            "What is the secret recipe for chocolate cake?",
            "--repo",
            str(synthetic_repo),
            "--backend",
            "mock",
        ],
    )
    assert res.exit_code == 0
    assert "The dead do not remember." in res.stdout


def test_cli_ask_raw_mode(synthetic_repo: Path) -> None:
    """CLI ask with --raw executes without guarded retry/repair."""
    res = runner.invoke(
        app,
        [
            "ask",
            "Why was request deprecated?",
            "--repo",
            str(synthetic_repo),
            "--backend",
            "mock",
            "--raw",
        ],
    )
    assert res.exit_code == 0


def test_cli_ask_non_git(non_git_dir: Path) -> None:
    """CLI ask fails cleanly on non-git directory with exit code 1."""
    res = runner.invoke(
        app,
        [
            "ask",
            "Why was request deprecated?",
            "--repo",
            str(non_git_dir),
            "--backend",
            "mock",
        ],
    )
    assert res.exit_code == 1
    assert "Error:" in res.stdout


def test_cli_ask_json_error(non_git_dir: Path) -> None:
    """CLI ask --json on error prints JSON error structure."""
    res = runner.invoke(
        app,
        [
            "ask",
            "test query",
            "--repo",
            str(non_git_dir),
            "--json",
        ],
    )
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    assert "error" in data


def test_cli_ask_reconsidering(synthetic_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI ask renders 'The spirits reconsider...' when retry is triggered."""
    from ghost_maintainer.backends.mock import MockBackend, MockMode

    mock_backend = MockBackend(mode=MockMode.RETRY_REPAIR)
    monkeypatch.setattr("ghost_maintainer.cli.get_backend", lambda _: mock_backend)
    monkeypatch.setattr("ghost_maintainer.seance.get_backend", lambda _: mock_backend)

    res = runner.invoke(
        app,
        [
            "ask",
            "Why was request deprecated?",
            "--repo",
            str(synthetic_repo),
            "--backend",
            "mock",
        ],
    )
    assert res.exit_code == 0
    assert "The spirits reconsider..." in res.stdout


def test_cli_seance_exit(synthetic_repo: Path) -> None:
    """CLI seance REPL accepts /exit and exits cleanly."""
    res = runner.invoke(
        app,
        ["seance", "--repo", str(synthetic_repo), "--backend", "mock"],
        input="/exit\n",
    )
    assert res.exit_code == 0
    assert "The Ghost Maintainer Seance" in res.stdout
    assert "The spirits return to the archive" in res.stdout


def test_cli_seance_help(synthetic_repo: Path) -> None:
    """CLI seance REPL /help displays available commands."""
    res = runner.invoke(
        app,
        ["seance", "--repo", str(synthetic_repo), "--backend", "mock"],
        input="/help\n/exit\n",
    )
    assert res.exit_code == 0
    assert "Available Seance Commands" in res.stdout
    assert "/evidence" in res.stdout
    assert "/backend" in res.stdout


def test_cli_seance_commands(synthetic_repo: Path) -> None:
    """CLI seance REPL commands /evidence, /backend, /mode, /clear execute cleanly."""
    script = "/evidence\n/backend mock\n/mode raw\n/clear\n/invalidcmd\n/exit\n"
    res = runner.invoke(
        app,
        ["seance", "--repo", str(synthetic_repo), "--backend", "mock"],
        input=script,
    )
    assert res.exit_code == 0
    assert "Evidence display hidden" in res.stdout
    assert "Backend switched to 'mock'" in res.stdout
    assert "Mode set to 'raw'" in res.stdout
    assert "Unknown command" in res.stdout


def test_cli_seance_query(synthetic_repo: Path) -> None:
    """CLI seance REPL executes questions and answers in departed maintainers voice."""
    script = "Why was request deprecated?\n/exit\n"
    res = runner.invoke(
        app,
        ["seance", "--repo", str(synthetic_repo), "--backend", "mock"],
        input=script,
    )
    assert res.exit_code == 0
    assert "Voices are fiction. Evidence is real." in res.stdout


def test_cli_seance_non_git(non_git_dir: Path) -> None:
    """CLI seance fails cleanly on non-git directory."""
    res = runner.invoke(app, ["seance", "--repo", str(non_git_dir)])
    assert res.exit_code == 1
    assert "Error:" in res.stdout


def test_cli_serve_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI serve launches uvicorn with configured host and port."""
    import uvicorn

    recorded_args: dict[str, Any] = {}

    def mock_run(target: str, **kwargs: Any) -> None:
        recorded_args["target"] = target
        recorded_args.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", mock_run)

    res = runner.invoke(app, ["serve", "--port", "6660", "--host", "127.0.0.1"])
    assert res.exit_code == 0
    assert recorded_args["target"] == "ghost_maintainer.server:app"
    assert recorded_args["port"] == 6660
    assert recorded_args["host"] == "127.0.0.1"
    assert "Listening on:" in res.stdout


def test_cli_serve_port_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI serve catches port conflict OSError and exits cleanly."""
    import uvicorn

    def mock_run(*_: Any, **__: Any) -> None:
        raise OSError("Address already in use")

    monkeypatch.setattr(uvicorn, "run", mock_run)

    res = runner.invoke(app, ["serve", "--port", "6660"])
    assert res.exit_code == 1
    assert "Port 6660 could not be bound" in res.stdout


def test_cli_eval_missing_file() -> None:
    """CLI eval fails cleanly when specified YAML file does not exist."""
    res = runner.invoke(app, ["eval", "missing_file_eval.yaml"])
    assert res.exit_code == 1
    assert "Error:" in res.stdout
    assert "not found" in res.stdout


def test_cli_eval_success(synthetic_repo: Path, tmp_path: Path) -> None:
    """CLI eval executes end-to-end on synthetic repository with valid YAML."""
    yaml_file = tmp_path / "test_eval.yaml"
    yaml_file.write_text("- question: Why was request deprecated?\n", encoding="utf-8")

    res = runner.invoke(app, ["eval", str(yaml_file), "--repo", str(synthetic_repo)])
    assert res.exit_code == 0
    assert "Honesty Benchmark" in res.stdout
