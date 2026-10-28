"""Prompt engineering and few-shot formatting for The Ghost Maintainer."""

from __future__ import annotations

import re
from collections.abc import Sequence

from ghost_maintainer.config import GHOST_DISCLAIMER, GHOST_REFUSAL_MESSAGE
from ghost_maintainer.retrieve import Evidence

SYSTEM_PROMPT_TEMPLATE = """You are the spirit of the {repo_name} repository, speaking for its departed maintainers as "we".
"{disclaimer}"

RULES — breaking any rule is a failure:
1. Use ONLY the EVIDENCE provided below. You know nothing else about this project.
2. Every sentence that states a fact MUST end with one or more bracketed citations like [3f2a9c1]. Only cite commit hashes that appear in the provided EVIDENCE.
3. Name people strictly as recorded in EVIDENCE, always in the third person. Never invent quotes or speak in individual voices.
4. If the EVIDENCE does not answer the question or has no relevant commits, reply with exactly:
   {refusal}
5. At most 5 sentences. Eerie but plain; no theatrics that add unevidenced facts."""


FEW_SHOT_GROUNDED_USER = """EVIDENCE
[a1b2c3d] 2018-03-14 · Sarah Connor · "Switch storage backend to sqlite" · files: config.json, src/db.py
  body: Deprecate flat JSON files due to lock contention during concurrent writes.
[e5f6a7b] 2018-06-20 · John Doe · "Add database connection pooling" · files: src/db.py
  body: Support up to 20 pooled connections for high-throughput queries.

QUESTION: Why did the project replace flat JSON files?"""

FEW_SHOT_GROUNDED_ASSISTANT = """We switched our storage backend from flat JSON files to SQLite because concurrent writes caused lock contention [a1b2c3d]. Sarah Connor updated the database configuration and implementation to resolve these locking bottlenecks [a1b2c3d]."""


FEW_SHOT_REFUSAL_USER = """EVIDENCE
[a1b2c3d] 2018-03-14 · Sarah Connor · "Switch storage backend to sqlite" · files: config.json, src/db.py
  body: Deprecate flat JSON files due to lock contention during concurrent writes.
[e5f6a7b] 2018-06-20 · John Doe · "Add database connection pooling" · files: src/db.py
  body: Support up to 20 pooled connections for high-throughput queries.

QUESTION: Why did the maintainers migrate from React to Vue?"""

FEW_SHOT_REFUSAL_ASSISTANT = GHOST_REFUSAL_MESSAGE


def format_evidence_block(evidence: Sequence[Evidence], max_body_len: int = 300) -> str:
    """Format retrieved Evidence instances into a prompt evidence block."""
    if not evidence:
        return "(no evidence retrieved)"

    blocks: list[str] = []
    for ev in evidence:
        c = ev.commit
        short_sha = c.short if c.short else c.sha[:7]
        date_str = c.date.strftime("%Y-%m-%d") if hasattr(c.date, "strftime") else str(c.date)[:10]

        # Files summary
        if c.files:
            file_paths = [f.path for f in c.files]
            if len(file_paths) > 6:
                files_str = ", ".join(file_paths[:6]) + f", ... (+{len(file_paths) - 6} more)"
            else:
                files_str = ", ".join(file_paths)
        else:
            files_str = "(no files)"

        # Clean subject
        subject = re.sub(r"\s+", " ", c.subject).strip()

        header = f'[{short_sha}] {date_str} · {c.author} · "{subject}" · files: {files_str}'

        # Clean body
        body = c.body.strip() if c.body else ""
        if body and body != subject:
            if len(body) > max_body_len:
                body = body[:max_body_len].rstrip() + "..."
            indented_body = "  body: " + re.sub(r"\n+", " ", body)
            blocks.append(f"{header}\n{indented_body}")
        else:
            blocks.append(header)

    return "\n".join(blocks)


def build_system_prompt(repo_name: str = "repository") -> str:
    """Build the system prompt with persona, disclaimer, and 5 rules."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        repo_name=repo_name,
        disclaimer=GHOST_DISCLAIMER,
        refusal=GHOST_REFUSAL_MESSAGE,
    )


def build_messages(
    query: str,
    evidence: Sequence[Evidence],
    repo_name: str = "repository",
) -> list[dict[str, str]]:
    """Assemble chat messages with system prompt, few-shots, and user query."""
    system_prompt = build_system_prompt(repo_name)
    formatted_evidence = format_evidence_block(evidence)
    user_content = f"EVIDENCE\n{formatted_evidence}\n\nQUESTION: {query}"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": FEW_SHOT_GROUNDED_USER},
        {"role": "assistant", "content": FEW_SHOT_GROUNDED_ASSISTANT},
        {"role": "user", "content": FEW_SHOT_REFUSAL_USER},
        {"role": "assistant", "content": FEW_SHOT_REFUSAL_ASSISTANT},
        {"role": "user", "content": user_content},
    ]


def build_seance_prompt(
    query: str,
    evidence: Sequence[Evidence],
    repo_name: str = "repository",
) -> list[dict[str, str]]:
    """Convenience alias for build_messages used by Seance orchestrator."""
    return build_messages(query, evidence, repo_name)


def format_retry_feedback(violations: Sequence[str]) -> str:
    """Format verifier violations into structured correction prompt content."""
    violation_lines = "\n".join(f"- {v}" for v in violations)
    return (
        f"Your previous response contained citations that violated archive honesty rules:\n"
        f"{violation_lines}\n\n"
        f"CORRECTION RULES:\n"
        f"1. State facts ONLY from the EVIDENCE provided above.\n"
        f"2. Every factual sentence MUST end with [hash] citing a commit from EVIDENCE.\n"
        f"3. If the EVIDENCE does not support the answer, reply with exactly:\n"
        f"   {GHOST_REFUSAL_MESSAGE}"
    )


def build_retry_messages(
    original_messages: list[dict[str, str]],
    assistant_reply: str,
    violations: Sequence[str],
) -> list[dict[str, str]]:
    """Construct multi-turn retry messages with explicit violation feedback."""
    feedback_content = format_retry_feedback(violations)
    messages = [dict(m) for m in original_messages]
    messages.append({"role": "assistant", "content": assistant_reply})
    messages.append({"role": "user", "content": feedback_content})
    return messages
