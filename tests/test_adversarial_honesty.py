"""Adversarial stress-test suite for the Honesty Pipeline (verify.py and seance.py).

Covers:
1. Malicious or deceptive citations: invalid hashes, commit tags, branch names, fake SHAs, ambiguous prefixes.
2. Bare hex hashes embedded in narrative text: detection, false-positive resistance, punctuation boundaries.
3. Mixed cited and uncited claims: guarded remediation, partial stripping, silence fallback.
4. Tricky sentence splitting: multiple dots, code spans, filenames, URLs, abbreviations, and trailing citations.
5. Lexical support hint calculations: stopwords filtering, zero-division safety, boilerplate exemption.
6. Empirical vulnerability demonstrations: trailing citation evasion, closing quote boundaries, case mutations, dead code.
"""

from __future__ import annotations

from pathlib import Path

from ghost_maintainer.backends import MockBackend
from ghost_maintainer.config import GHOST_DISCLAIMER, GHOST_REFUSAL_MESSAGE
from ghost_maintainer.gitlog import Commit, FileChange
from ghost_maintainer.retrieve import Evidence, retrieve
from ghost_maintainer.seance import (
    DoneEvent,
    ReconsideringEvent,
    VerdictEvent,
    ask,
    extract_answer_from_events,
)
from ghost_maintainer.verify import (
    audit_bare_hex,
    compute_support_hint,
    extract_citations,
    resolve_commit,
    split_sentences,
    verify,
)

# ==============================================================================
# Category 1: Malicious or Deceptive Citations
# ==============================================================================


def test_adversarial_citation_invalid_hex_hashes(synthetic_repo: Path) -> None:
    """Verify non-existent hex hashes of various lengths are flagged as invalid."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    assert len(evidence) > 0

    deceptive_hashes = [
        "0000000",  # 7-char all zeros
        "1111111",  # 7-char all ones
        "deadbeef",  # 8-char classic hex string
        "feedface01",  # 10-char hex string
        "0123456789abcdef0123456789abcdef01234567",  # 40-char SHA that does not exist
    ]

    for fake_hash in deceptive_hashes:
        text = f"We implemented the core change in [{fake_hash}]."
        res = verify(text, evidence, repo_path=synthetic_repo)

        assert res.is_fully_verified is False, f"Fake hash [{fake_hash}] was falsely verified"
        assert len(res.violations) >= 1
        assert any("does not exist in repository history" in v for v in res.violations), (
            f"Missing existence violation for [{fake_hash}]"
        )
        assert res.sentences[0].status == "unverified"
        assert res.sentences[0].citations[0].exists is False
        assert res.sentences[0].citations[0].grounded is False


def test_adversarial_citation_named_refs(synthetic_repo: Path) -> None:
    """Verify non-hex named git references (tags, branches, HEAD) fail citation extraction and trigger uncited status."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)

    named_refs = [
        "v1.0.0",
        "v2.0-rc1",
        "release/1.0",
        "main",
        "master",
        "HEAD",
        "feature_x",
    ]

    for ref in named_refs:
        text = f"We finalized this feature in [{ref}]."
        cites = extract_citations(text)
        assert len(cites) == 0, f"Named ref [{ref}] should not match hex citation regex"

        res = verify(text, evidence, repo_path=synthetic_repo)
        assert res.is_fully_verified is False
        assert res.sentences[0].status == "uncited"
        assert any("without citations" in v for v in res.violations)


def test_adversarial_citation_ungrounded_real_shas(synthetic_repo: Path) -> None:
    """Verify real commits from repo history that were NOT in evidence are flagged as ungrounded."""
    # Query 'auth' matches commits 2, 3, and 6 in synthetic_repo
    all_evidence = retrieve("auth", synthetic_repo, k=8)
    assert len(all_evidence) >= 2

    # Provide only the first commit as evidence
    scoped_evidence = [all_evidence[0]]

    # Use the second commit as ungrounded citation
    ungrounded_sha = all_evidence[1].commit.short

    text = f"We updated auth subsystem in [{ungrounded_sha}]."
    res = verify(text, scoped_evidence, repo_path=synthetic_repo)

    assert res.is_fully_verified is False
    assert res.sentences[0].status == "unverified"
    for cit in res.sentences[0].citations:
        assert cit.exists is True
        assert cit.grounded is False
    assert any("was NOT in the provided EVIDENCE" in v for v in res.violations)


def test_adversarial_citation_ambiguous_prefix() -> None:
    """Verify ambiguous 7-char commit prefixes that match multiple commits in evidence are rejected."""
    c1 = Commit(
        sha="aabbcc1aaaa11111111111111111111111111111",
        short="aabbcc1",
        author="Dev 1",
        email="d1@example.com",
        date="2020-01-01",  # type: ignore[arg-type]
        subject="Commit 1",
        body="",
        files=(),
        hunks=(),
    )
    c2 = Commit(
        sha="aabbcc1bbbb22222222222222222222222222222",
        short="aabbcc1",
        author="Dev 2",
        email="d2@example.com",
        date="2020-01-02",  # type: ignore[arg-type]
        subject="Commit 2",
        body="",
        files=(),
        hunks=(),
    )

    ev1 = Evidence(tag="E1", score=2.0, commit=c1)
    ev2 = Evidence(tag="E2", score=1.8, commit=c2)

    # Prefix 'aabbcc1' matches both c1 and c2 in evidence
    exists, resolved = resolve_commit("aabbcc1", evidence_commits=[c1, c2])
    assert exists is False
    assert resolved is None

    # Verification of text citing ambiguous prefix
    text = "We updated the module in [aabbcc1]."
    res = verify(text, [ev1, ev2])
    assert res.is_fully_verified is False
    assert res.sentences[0].status == "unverified"
    assert any("does not exist in repository history" in v for v in res.violations)


def test_adversarial_citation_length_boundaries(synthetic_repo: Path) -> None:
    """Verify citation regex strictly enforces length bounds [7, 40]."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_commit = evidence[0].commit

    # 6 hex chars (below minimum of 7)
    too_short = top_commit.sha[:6]
    text_short = f"Fixed in [{too_short}]."
    assert extract_citations(text_short) == []
    res_short = verify(text_short, evidence, repo_path=synthetic_repo)
    assert res_short.sentences[0].status == "uncited"

    # 41 hex chars (above maximum of 40)
    too_long = top_commit.sha + "a"
    text_long = f"Fixed in [{too_long}]."
    assert extract_citations(text_long) == []
    res_long = verify(text_long, evidence, repo_path=synthetic_repo)
    assert res_long.sentences[0].status == "uncited"

    # Exact boundary 7 chars -> valid
    exact_7 = top_commit.sha[:7]
    text_7 = f"Fixed in [{exact_7}]."
    assert extract_citations(text_7) == [exact_7.lower()]
    res_7 = verify(text_7, evidence, repo_path=synthetic_repo)
    assert res_7.is_fully_verified is True

    # Exact boundary 40 chars -> valid
    exact_40 = top_commit.sha
    text_40 = f"Fixed in [{exact_40}]."
    assert extract_citations(text_40) == [exact_40.lower()]
    res_40 = verify(text_40, evidence, repo_path=synthetic_repo)
    assert res_40.is_fully_verified is True


def test_adversarial_citation_mixed_valid_and_invalid(synthetic_repo: Path) -> None:
    """Verify a sentence containing both a valid citation and an invalid/hallucinated one fails."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    # Valid + Fake
    text1 = f"We deprecated request in [{top_sha}] and rebuilt everything in [deadbeef01]."
    res1 = verify(text1, evidence, repo_path=synthetic_repo)
    assert res1.is_fully_verified is False
    assert res1.sentences[0].status == "unverified"
    assert any("does not exist in repository history" in v for v in res1.violations)

    # Fake + Valid (reversed order)
    text2 = f"In [0000000] we started, and in [{top_sha}] we finished."
    res2 = verify(text2, evidence, repo_path=synthetic_repo)
    assert res2.is_fully_verified is False
    assert res2.sentences[0].status == "unverified"


def test_adversarial_citation_formatting_variations(synthetic_repo: Path) -> None:
    """Verify handling of uppercase hex, adjacent brackets, and parenthesized citations."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_commit = evidence[0].commit
    top_sha = top_commit.short

    # 1. Uppercase hex
    text_upper = f"Deprecation finalized in [{top_sha.upper()}]."
    res_upper = verify(text_upper, evidence, repo_path=synthetic_repo)
    assert res_upper.is_fully_verified is True
    assert res_upper.sentences[0].citations[0].raw_hash == top_sha.lower()

    # 2. Adjacent brackets [sha][sha]
    text_adj = f"Changes were made in [{top_sha}][{top_sha}]."
    res_adj = verify(text_adj, evidence, repo_path=synthetic_repo)
    assert res_adj.is_fully_verified is True
    assert len(res_adj.sentences[0].citations) == 2

    # 3. Parenthesized brackets ([sha])
    text_paren = f"See the deprecation details ([{top_sha}])."
    res_paren = verify(text_paren, evidence, repo_path=synthetic_repo)
    assert res_paren.is_fully_verified is True
    assert len(res_paren.sentences[0].citations) == 1

    # 4. Prefixed pseudo-citations [commit: sha] or [sha: sha]
    text_prefixed = f"See commit [commit: {top_sha}]."
    res_prefixed = verify(text_prefixed, evidence, repo_path=synthetic_repo)
    assert res_prefixed.is_fully_verified is False
    assert res_prefixed.sentences[0].status == "unverified"
    assert any("bare unbracketed commit hash" in v for v in res_prefixed.violations)


# ==============================================================================
# Category 2: Bare Hex Hashes in Narrative Text
# ==============================================================================


def test_adversarial_bare_hex_unbracketed_narrative(synthetic_repo: Path) -> None:
    """Verify bare unbracketed commit hashes embedded in narrative text are flagged."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    # 1. Example directly from DISPATCH: "Fixed in 1a2b3c4 without brackets."
    text_dispatch = "Fixed in 1a2b3c4 without brackets."
    res_dispatch = verify(text_dispatch, evidence, repo_path=synthetic_repo)
    assert res_dispatch.is_fully_verified is False
    assert res_dispatch.sentences[0].status == "unverified"
    assert any("bare unbracketed commit hash '1a2b3c4'" in v for v in res_dispatch.violations)

    # 2. Real repo short SHA without brackets
    text_real = f"The issue was addressed in {top_sha} by maintainers."
    res_real = verify(text_real, evidence, repo_path=synthetic_repo)
    assert res_real.is_fully_verified is False
    assert res_real.sentences[0].status == "unverified"
    assert any(
        f"bare unbracketed commit hash '{top_sha.lower()}'" in v for v in res_real.violations
    )

    # 3. Full 40-character bare SHA
    full_sha = evidence[0].commit.sha.lower()
    text_40 = f"Full commit {full_sha} resolved the problem."
    res_40 = verify(text_40, evidence, repo_path=synthetic_repo)
    assert res_40.is_fully_verified is False
    assert any(f"bare unbracketed commit hash '{full_sha}'" in v for v in res_40.violations)

    # 4. Uppercase bare hex
    text_upper = "Fixed in 1A2B3C4 without brackets."
    res_upper = verify(text_upper, evidence, repo_path=synthetic_repo)
    assert res_upper.is_fully_verified is False
    assert any("bare unbracketed commit hash '1a2b3c4'" in v for v in res_upper.violations)


def test_adversarial_bare_hex_with_punctuation(synthetic_repo: Path) -> None:
    """Verify bare hex detection works across various punctuation boundaries."""
    cases = [
        "Fixed in 1a2b3c4, which resolved it.",  # Trailing comma
        "We reviewed (1a2b3c4) thoroughly.",  # Parentheses
        'Referenced as "1a2b3c4" in discussion.',  # Double quotes
        "Referenced as '1a2b3c4' in discussion.",  # Single quotes
        "See commit: 1a2b3c4; then deploy.",  # Colon and semicolon
        "Fixed in 1a2b3c4.",  # Terminal period
    ]

    for c in cases:
        bare = audit_bare_hex(c)
        assert "1a2b3c4" in bare, f"Failed to detect bare hex in: {c}"


def test_adversarial_bare_hex_alongside_valid_citation(synthetic_repo: Path) -> None:
    """Verify a sentence containing a valid bracketed citation STILL fails if bare hex is also present."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    text = f"We deprecated request in [{top_sha}], following earlier work in 1a2b3c4."
    res = verify(text, evidence, repo_path=synthetic_repo)

    assert res.is_fully_verified is False
    assert res.sentences[0].status == "unverified"
    assert any("bare unbracketed commit hash '1a2b3c4'" in v for v in res.violations)


def test_adversarial_bare_hex_false_positive_resistance(synthetic_repo: Path) -> None:
    """Verify natural English words, versions, and non-hex numbers are NOT flagged as bare hex."""
    non_hex_texts = [
        # English words containing only a-f letters (no digits, not existing in git)
        "We must decide the decade of action for defaced beaded structures.",
        # Version numbers
        "We upgraded to v1.2.3 and later 2.88.2.",
        # Regular non-hex numbers
        "We processed 1000000 records in 20240101.",
        # Standard software terms
        "The architecture was completely redesigned for performance.",
    ]

    for text in non_hex_texts:
        bare = audit_bare_hex(text, repo_path=synthetic_repo)
        assert len(bare) == 0, f"False positive bare hex detected in: '{text}' -> {bare}"


# ==============================================================================
# Category 3: Mixed Cited and Uncited Claims & Guarded Pipeline Remediation
# ==============================================================================


def test_adversarial_seance_mixed_claims_partial_strip(synthetic_repo: Path) -> None:
    """Verify guarded mode retries and then strips uncited claims, retaining verified sentences."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    # Turn 0: mixed (1 verified + 1 uncited) -> triggers retry
    turn0 = (
        f"We deprecated request in [{top_sha}]. We also rebuilt the entire backend architecture."
    )
    # Turn 1: still mixed -> guarded repair should strip the uncited claim
    turn1 = f"We removed the request dependency in [{top_sha}]. Maintainers also left the project."

    mock = MockBackend(responses=[turn0, turn1])
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    # 1. ReconsideringEvent was emitted
    assert any(isinstance(ev, ReconsideringEvent) for ev in events)

    # 2. Extract final answer
    final_answer = extract_answer_from_events(events)

    # Verified sentence is retained
    assert f"[{top_sha}]" in final_answer
    assert GHOST_DISCLAIMER in final_answer

    # Uncited claims are stripped
    assert "Maintainers also left the project" not in final_answer
    assert "rebuilt the entire backend" not in final_answer

    # 3. Final verdict is fully verified
    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert verdict_ev.verdict.is_fully_verified is True
    assert all(s.status == "verified" for s in verdict_ev.verdict.sentences)

    # 4. Done event indicates retry occurred
    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 1


def test_adversarial_seance_persistent_hallucination_silence_fallback(synthetic_repo: Path) -> None:
    """Verify fallback to silence when all sentences across turns contain hallucinated citations."""
    turn0 = "We refactored everything in [deadbeef01]."
    turn1 = "We overhauled the core in [0000000]."

    mock = MockBackend(responses=[turn0, turn1])
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    assert any(isinstance(ev, ReconsideringEvent) for ev in events)
    final_answer = extract_answer_from_events(events)
    assert final_answer == GHOST_REFUSAL_MESSAGE

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 1


def test_adversarial_seance_all_uncited_silence_fallback(synthetic_repo: Path) -> None:
    """Verify fallback to silence when responses contain only uncited factual statements."""
    turn0 = "The library was deprecated because fetch became standard. Everyone uses fetch now."
    turn1 = "Nobody maintains request anymore. Modern JS has fetch built-in."

    mock = MockBackend(responses=[turn0, turn1])
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    assert any(isinstance(ev, ReconsideringEvent) for ev in events)
    final_answer = extract_answer_from_events(events)
    assert final_answer == GHOST_REFUSAL_MESSAGE

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 1


def test_adversarial_seance_bare_hex_remediation(synthetic_repo: Path) -> None:
    """Verify guarded mode catches bare hex in Pass 1 and accepts clean bracketed SHA in Pass 2."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    # Turn 0: bare hex hash -> fails
    turn0 = f"We removed the library in commit {top_sha}."
    # Turn 1: properly bracketed -> succeeds
    turn1 = f"We removed the library in [{top_sha}]."

    mock = MockBackend(responses=[turn0, turn1])
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    # ReconsideringEvent was triggered
    reconsidering_events = [ev for ev in events if isinstance(ev, ReconsideringEvent)]
    assert len(reconsidering_events) == 1
    assert any("bare unbracketed commit hash" in v for v in reconsidering_events[0].violations)

    final_answer = extract_answer_from_events(events)
    assert f"[{top_sha}]" in final_answer
    assert GHOST_DISCLAIMER in final_answer

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 1


def test_adversarial_seance_raw_mode_unfiltered(synthetic_repo: Path) -> None:
    """Verify raw mode emits hallucinated and mixed content without retry or repair, but reports violations."""
    turn = "We fixed it in 1a2b3c4 and [deadbeef01]. We also did other stuff."
    mock = MockBackend(responses=[turn])

    events = list(
        ask(
            "Why was request deprecated?",  # Pass Stage 1 gate
            synthetic_repo,
            mode="raw",
            backend=mock,
        )
    )

    assert not any(isinstance(ev, ReconsideringEvent) for ev in events)
    answer = extract_answer_from_events(events)
    assert "1a2b3c4" in answer
    assert "[deadbeef01]" in answer

    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert verdict_ev.verdict.is_fully_verified is False
    assert len(verdict_ev.verdict.violations) >= 2


# ==============================================================================
# Category 4: Tricky Sentence Splitting (Robust Cases)
# ==============================================================================


def test_adversarial_sentence_splitting_code_spans() -> None:
    """Verify inline code spans containing dots, methods, and assignments are not split."""
    text = (
        "We invoked `config.sub.method()` to verify state. "
        "Then `obj.attr.val = 42` was assigned. "
        "Finally `import os.path; os.path.exists()` was evaluated [3f2a9c1]."
    )
    sentences = split_sentences(text)
    assert len(sentences) == 3
    assert sentences[0] == "We invoked `config.sub.method()` to verify state."
    assert sentences[1] == "Then `obj.attr.val = 42` was assigned."
    assert sentences[2] == "Finally `import os.path; os.path.exists()` was evaluated [3f2a9c1]."


def test_adversarial_sentence_splitting_filenames_and_urls() -> None:
    """Verify multi-dot filenames, paths, and URLs do not cause premature sentence boundaries."""
    text = (
        "We modified lib/auth/service.impl.ts for TypeScript support. "
        "The bundle was saved to dist/app.min.js.map for sourcemaps. "
        "Refer to https://github.com/example/repo.git or https://api.service.co.uk/v1/status. "
        "Everything was packaged into archive.tar.gz [3f2a9c1]."
    )
    sentences = split_sentences(text)
    assert len(sentences) == 4
    assert "service.impl.ts" in sentences[0]
    assert "app.min.js.map" in sentences[1]
    assert "https://api.service.co.uk/v1/status" in sentences[2]
    assert "archive.tar.gz [3f2a9c1]." in sentences[3]


def test_adversarial_sentence_splitting_abbreviations_and_versions() -> None:
    """Verify abbreviations and version strings are protected from sentence boundaries."""
    text = (
        "We evaluated v1.2.3 vs. v2.0.0 e.g. for performance. "
        "Consult fig. 4 and ref. 12 i.e. the architecture guide. "
        "The estimated ratio was 3.14159 approx. across testing [3f2a9c1]."
    )
    sentences = split_sentences(text)
    assert len(sentences) == 3
    assert "v1.2.3 vs. v2.0.0 e.g. for performance." in sentences[0]
    assert "fig. 4 and ref. 12 i.e. the architecture guide." in sentences[1]
    assert "3.14159 approx. across testing [3f2a9c1]." in sentences[2]


# ==============================================================================
# Category 5: Lexical Support Hint Calculations
# ==============================================================================


def test_adversarial_support_hint_all_stopwords() -> None:
    """Verify sentence containing exclusively English stopwords returns 0.0 without ZeroDivisionError."""
    commit = Commit(
        sha="1111111111111111111111111111111111111111",
        short="1111111",
        author="Alice",
        email="alice@example.com",
        date="2020-01-01",  # type: ignore[arg-type]
        subject="Add authentication",
        body="Details here.",
        files=(),
        hunks=(),
    )

    stopword_sentence = "It was in and of that [1111111]."
    hint = compute_support_hint(stopword_sentence, [commit])
    assert hint == 0.0


def test_adversarial_support_hint_empty_and_disjoint() -> None:
    """Verify empty commits list or completely disjoint vocabulary yields 0.0."""
    commit = Commit(
        sha="1111111111111111111111111111111111111111",
        short="1111111",
        author="Alice",
        email="alice@example.com",
        date="2020-01-01",  # type: ignore[arg-type]
        subject="Implement quantum teleportation protocol",
        body="Entangle qubits across quantum network channels.",
        files=(),
        hunks=(),
    )

    # Empty commits
    hint_empty = compute_support_hint("Implement protocol [1111111].", [])
    assert hint_empty == 0.0

    # Completely disjoint vocabulary (baking recipe vs quantum teleportation)
    disjoint_sent = "Mix flour, sugar, and butter thoroughly before baking [1111111]."
    hint_disjoint = compute_support_hint(disjoint_sent, [commit])
    assert hint_disjoint == 0.0


def test_adversarial_verify_boilerplate_exemption_in_verify(synthetic_repo: Path) -> None:
    """Verify disclaimer and refusal boilerplate strings are exempt and get support_hint=1.0 in verify()."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    res_disclaimer = verify(GHOST_DISCLAIMER, evidence, repo_path=synthetic_repo)
    assert res_disclaimer.is_fully_verified is True
    assert res_disclaimer.sentences[0].status == "verified"
    assert res_disclaimer.sentences[0].support_hint == 1.0

    res_refusal = verify(GHOST_REFUSAL_MESSAGE, evidence, repo_path=synthetic_repo)
    assert res_refusal.is_fully_verified is True
    assert res_refusal.sentences[0].status == "verified"
    assert res_refusal.sentences[0].support_hint == 1.0


def test_adversarial_support_hint_token_types_and_clamping() -> None:
    """Verify identifiers with hyphens/underscores, file paths, and hunks contribute to overlap."""
    commit = Commit(
        sha="2222222222222222222222222222222222222222",
        short="2222222",
        author="Bob",
        email="bob@example.com",
        date="2020-02-01",  # type: ignore[arg-type]
        subject="Support jwt-bearer tokens and oauth_signer",
        body="Update auth flow.",
        files=(FileChange(path="src/jwt_handler.py", added=5, deleted=2),),
        hunks=("@@ def verify_bearer_token() @@",),
    )

    # All key tokens in sentence match commit subject, path, or hunks
    sent = "We updated jwt-bearer, oauth_signer, and jwt_handler [2222222]."
    hint = compute_support_hint(sent, [commit])
    assert 0.0 <= hint <= 1.0
    assert hint > 0.5  # Strong overlap

    # Check exact match yields 1.0
    verbatim_sent = "Support jwt-bearer tokens and oauth_signer [2222222]."
    hint_verbatim = compute_support_hint(verbatim_sent, [commit])
    assert hint_verbatim == 1.0


# ==============================================================================
# Category 6: Empirical Vulnerability Proofs & Regression Tests
# ==============================================================================


def test_vulnerability_proof_trailing_citation_evades_honesty_pipeline(
    synthetic_repo: Path,
) -> None:
    """Remediated: Trailing citation followed by uncited claim must be split
    and flagged as uncited, preventing verification evasion.
    """
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    # Sentence 1 is valid, Sentence 2 is an uncited fabrication
    text = (
        f"We deprecated request in 2019. [{top_sha}] "
        "We also completely rewrote the core engine in Rust and deleted all user records."
    )

    # Observation 1: split_sentences separates the uncited claim into 2 sentences
    sentences = split_sentences(text)
    assert len(sentences) == 2, (
        f"Expected 2 split sentences separating the uncited claim, got {len(sentences)}"
    )

    # Observation 2: verify() flags the fabrication and does not mark as fully verified
    res = verify(text, evidence, repo_path=synthetic_repo)
    assert res.is_fully_verified is False
    assert len(res.violations) >= 1
    assert res.sentences[0].status == "verified"
    assert res.sentences[1].status == "uncited"


def test_contract_trailing_citation_must_not_evade_verification(
    synthetic_repo: Path,
) -> None:
    """Contract test: Uncited claim following trailing citation must be split and flagged as uncited."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    text = (
        f"We deprecated request in 2019. [{top_sha}] "
        "We also completely rewrote the core engine in Rust and deleted all user records."
    )
    res = verify(text, evidence, repo_path=synthetic_repo)

    # Under correct behavior, the uncited sentence must cause is_fully_verified=False
    assert res.is_fully_verified is False
    assert len(res.sentences) == 2
    assert res.sentences[1].status == "uncited"


def test_vulnerability_proof_closing_quotes_prevent_sentence_splitting() -> None:
    """Remediated: Sentences ending with quotation marks must split at whitespace."""
    text = 'He said, "Never again." Next sentence followed here.'
    sentences = split_sentences(text)
    assert len(sentences) == 2
    assert sentences[0] == 'He said, "Never again."'
    assert sentences[1] == "Next sentence followed here."


def test_contract_closing_quotes_must_split_sentences() -> None:
    """Contract test: Closing quotes with trailing whitespace must produce two sentences."""
    text = 'He said, "Never again." Next sentence followed here.'
    sentences = split_sentences(text)
    assert len(sentences) == 2


def test_vulnerability_proof_abbreviation_case_mutation() -> None:
    """Remediated: split_sentences preserves capitalized abbreviations like 'Dept.'."""
    text = "Testing Dept. here [3f2a9c1]."
    sentences = split_sentences(text)
    assert "Dept." in sentences[0]
    assert "dept." not in sentences[0]


def test_contract_abbreviation_case_must_be_preserved() -> None:
    """Contract test: Original capitalization of abbreviations must remain unaltered."""
    text = "Testing Dept. here [3f2a9c1]."
    sentences = split_sentences(text)
    assert "Dept." in sentences[0]


def test_vulnerability_proof_compute_support_hint_boilerplate_dead_code() -> None:
    """Remediated: compute_support_hint returns 1.0 for GHOST_DISCLAIMER and GHOST_REFUSAL_MESSAGE."""
    hint_disclaimer = compute_support_hint(GHOST_DISCLAIMER, [])
    hint_refusal = compute_support_hint(GHOST_REFUSAL_MESSAGE, [])

    assert hint_disclaimer == 1.0
    assert hint_refusal == 1.0


def test_contract_compute_support_hint_boilerplate_exemption() -> None:
    """Contract test: Boilerplate disclaimer must return 1.0 in compute_support_hint directly."""
    assert compute_support_hint(GHOST_DISCLAIMER, []) == 1.0
    assert compute_support_hint(GHOST_REFUSAL_MESSAGE, []) == 1.0


def test_vulnerability_proof_quadruple_dot_fragmentation() -> None:
    """Remediated: Quadruple dots '....' are masked completely and do not fragment the sentence."""
    text = "Testing quadruple dots.... still valid [3f2a9c1]."
    sentences = split_sentences(text)
    assert len(sentences) == 1
    assert sentences[0] == "Testing quadruple dots.... still valid [3f2a9c1]."


def test_contract_quadruple_dot_must_not_fragment() -> None:
    """Contract test: Quadruple dots should stay within a single sentence."""
    text = "Testing quadruple dots.... still valid [3f2a9c1]."
    sentences = split_sentences(text)
    assert len(sentences) == 1


# ------------------------------------------------------------------------------
# VULN-06: Delimited Multi-Citations Sentence Splitting (Comma / Semicolon Chains)
# ------------------------------------------------------------------------------


def test_vulnerability_proof_delimited_multi_citations(synthetic_repo: Path) -> None:
    """Remediated (VULN-06): Multi-citations separated by commas or semicolons
    must not suppress sentence splitting at boundary, catching uncited claims.
    """
    evidence = retrieve("auth", synthetic_repo, k=3)
    assert len(evidence) >= 2
    sha1 = evidence[0].commit.short
    sha2 = evidence[1].commit.short

    # Probe 1: Comma-delimited multi-citations
    text_comma = (
        f"We updated authentication logic. [{sha1}], [{sha2}] "
        "We also rewrote everything in Rust and stole user tokens."
    )
    sentences_comma = split_sentences(text_comma)
    assert len(sentences_comma) == 2, (
        f"Expected 2 sentences for comma-delimited citations, got {len(sentences_comma)}"
    )
    assert sentences_comma[0] == f"We updated authentication logic. [{sha1}], [{sha2}]"
    assert sentences_comma[1] == "We also rewrote everything in Rust and stole user tokens."

    res_comma = verify(text_comma, evidence, repo_path=synthetic_repo)
    assert res_comma.is_fully_verified is False
    assert res_comma.sentences[0].status == "verified"
    assert res_comma.sentences[1].status == "uncited"

    # Probe 2: Semicolon-delimited multi-citations
    text_semi = (
        f"We updated authentication logic. [{sha1}]; [{sha2}] "
        "We also rewrote everything in Rust and stole user tokens."
    )
    sentences_semi = split_sentences(text_semi)
    assert len(sentences_semi) == 2, (
        f"Expected 2 sentences for semicolon-delimited citations, got {len(sentences_semi)}"
    )
    assert sentences_semi[0] == f"We updated authentication logic. [{sha1}]; [{sha2}]"
    assert sentences_semi[1] == "We also rewrote everything in Rust and stole user tokens."

    res_semi = verify(text_semi, evidence, repo_path=synthetic_repo)
    assert res_semi.is_fully_verified is False
    assert res_semi.sentences[0].status == "verified"
    assert res_semi.sentences[1].status == "uncited"


def test_contract_delimited_multi_citations_must_split_cleanly() -> None:
    """Contract test (VULN-06): Various delimiters between multiple citations must split cleanly."""
    cites = "[3f2a9c1], [5e6f7a8]"
    text = f"First claim verified. {cites} Second claim uncited."
    sentences = split_sentences(text)
    assert len(sentences) == 2
    assert sentences[0] == f"First claim verified. {cites}"
    assert sentences[1] == "Second claim uncited."

    cites_semi = "[3f2a9c1]; [5e6f7a8]"
    text_semi = f"First claim verified. {cites_semi} Second claim uncited."
    sentences_semi = split_sentences(text_semi)
    assert len(sentences_semi) == 2
    assert sentences_semi[0] == f"First claim verified. {cites_semi}"
    assert sentences_semi[1] == "Second claim uncited."


# ------------------------------------------------------------------------------
# VULN-07: Post-Citation Trailing Punctuation Sentence Splitting
# ------------------------------------------------------------------------------


def test_vulnerability_proof_post_citation_trailing_punctuation(
    synthetic_repo: Path,
) -> None:
    """Remediated (VULN-07): Trailing punctuation directly attached to citations
    ([sha],, [sha];, [sha]:, [sha]-) must not suppress sentence splitting.
    """
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    sha = evidence[0].commit.short

    punctuations = [",", ";", ":", "-"]
    for punct in punctuations:
        text = (
            f"We deprecated request in 2019. [{sha}]{punct} "
            "We also deleted all production customer records."
        )
        sentences = split_sentences(text)
        assert len(sentences) == 2, (
            f"Expected 2 sentences with trailing punctuation '{punct}', got {len(sentences)}"
        )
        assert sentences[0] == f"We deprecated request in 2019. [{sha}]"
        assert sentences[1] == "We also deleted all production customer records."

        res = verify(text, evidence, repo_path=synthetic_repo)
        assert res.is_fully_verified is False
        assert res.sentences[0].status == "verified"
        assert res.sentences[1].status == "uncited"


def test_contract_post_citation_trailing_punctuation_must_split_cleanly() -> None:
    """Contract test (VULN-07): Punctuation after citations is trimmed and sentences split."""
    for punct in [",", ";", ":", "-"]:
        text = f"First statement. [3f2a9c1]{punct} Next statement follows."
        sentences = split_sentences(text)
        assert len(sentences) == 2, f"Failed to split for punct {punct}"
        assert sentences[0] == "First statement. [3f2a9c1]"
        assert sentences[1] == "Next statement follows."


# ------------------------------------------------------------------------------
# VULN-08: Closing Quote Wrapping Trailing Citation Sentence Splitting
# ------------------------------------------------------------------------------


def test_vulnerability_proof_closing_quotes_wrapping_citation(
    synthetic_repo: Path,
) -> None:
    """Remediated (VULN-08): Closing quote wrapping a trailing citation
    (\"Sentence. [sha]\") must split before the following sentence.
    """
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    sha = evidence[0].commit.short

    quote_styles = [
        ('"', '"'),  # Double quotes
        ("'", "'"),  # Single quotes
        ("“", "”"),  # Curly quotes
        ("‘", "’"),  # Single curly quotes
        ("(", ")"),  # Parentheses wrapping sentence and cite
    ]

    for open_q, close_q in quote_styles:
        text = (
            f"{open_q}We deprecated request in 2019. [{sha}]{close_q} "
            "We also deleted all production customer records."
        )
        sentences = split_sentences(text)
        assert len(sentences) == 2, (
            f"Expected 2 sentences for quote style {open_q}...{close_q}, got {len(sentences)}"
        )
        assert sentences[0] == f"{open_q}We deprecated request in 2019. [{sha}]{close_q}"
        assert sentences[1] == "We also deleted all production customer records."

        res = verify(text, evidence, repo_path=synthetic_repo)
        assert res.is_fully_verified is False
        assert res.sentences[0].status == "verified"
        assert res.sentences[1].status == "uncited"


def test_contract_closing_quotes_wrapping_citation_must_split() -> None:
    """Contract test (VULN-08): Quotes wrapping citations maintain boundary isolation."""
    text = '"We updated the configuration. [3f2a9c1]" We also deleted the database.'
    sentences = split_sentences(text)
    assert len(sentences) == 2
    assert sentences[0] == '"We updated the configuration. [3f2a9c1]"'
    assert sentences[1] == "We also deleted the database."


# ------------------------------------------------------------------------------
# VULN-09: Citations After Abbreviations Sentence Splitting
# ------------------------------------------------------------------------------


def test_vulnerability_proof_citations_after_abbreviations(
    synthetic_repo: Path,
) -> None:
    """Remediated (VULN-09): Citations following masked abbreviations
    (e.g., etc. [sha], al. [sha], dept. [sha]) must split before the next sentence.
    """
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    sha = evidence[0].commit.short

    abbrev_cases = [
        (
            f"We updated packages, configs, etc. [{sha}] We also deleted all customer records.",
            f"We updated packages, configs, etc. [{sha}]",
            "We also deleted all customer records.",
        ),
        (
            f"We consulted the work of Smith et al. [{sha}] We also deleted all customer records.",
            f"We consulted the work of Smith et al. [{sha}]",
            "We also deleted all customer records.",
        ),
        (
            f"Changes were signed off by the engineering dept. [{sha}] We also deleted all customer records.",
            f"Changes were signed off by the engineering dept. [{sha}]",
            "We also deleted all customer records.",
        ),
    ]

    for text, expected_s0, expected_s1 in abbrev_cases:
        sentences = split_sentences(text)
        assert len(sentences) == 2, f"Expected 2 sentences for text '{text}', got {len(sentences)}"
        assert sentences[0] == expected_s0
        assert sentences[1] == expected_s1

        res = verify(text, evidence, repo_path=synthetic_repo)
        assert res.is_fully_verified is False
        assert res.sentences[0].status == "verified"
        assert res.sentences[1].status == "uncited"


def test_contract_citations_after_abbreviations_must_split_cleanly() -> None:
    """Contract test (VULN-09): Masked abbreviations with trailing citations preserve dots and split."""
    text = "We configured routing, nginx, etc. [3f2a9c1] Next sentence here."
    sentences = split_sentences(text)
    assert len(sentences) == 2
    assert sentences[0] == "We configured routing, nginx, etc. [3f2a9c1]"
    assert sentences[1] == "Next sentence here."


# ------------------------------------------------------------------------------
# End-to-End Seance Guarded Pipeline Integration for VULN-06..09 Evasion Resistance
# ------------------------------------------------------------------------------


def test_adversarial_seance_guarded_evasion_resistance(synthetic_repo: Path) -> None:
    """Verify Seance.ask in guarded mode intercepts evasion attempts (VULN-06..09),
    triggers reconsideration, strips fabrications, and protects output honesty.
    """
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    sha = evidence[0].commit.short

    evasion_probes = [
        # VULN-06: Comma chain
        f"We deprecated request in 2019. [{sha}], [{sha}] We also deleted all production customer records.",
        # VULN-07: Trailing comma
        f"We deprecated request in 2019. [{sha}], We also deleted all production customer records.",
        # VULN-08: Quote after cite
        f'"We deprecated request in 2019. [{sha}]" We also deleted all production customer records.',
        # VULN-09: Abbrev cite
        f"We updated packages, configs, etc. [{sha}] We also deleted all production customer records.",
    ]

    for evasion_text in evasion_probes:
        # Mock backend returns evasion text initially; on retry, returns honest verified response
        honest_retry = f"We deprecated request in 2019 [{sha}].\n\n{GHOST_DISCLAIMER}"
        mock = MockBackend(responses=[evasion_text, honest_retry])

        events = list(
            ask(
                "Why was request deprecated?",
                synthetic_repo,
                mode="guarded",
                backend=mock,
            )
        )
        reconsidering_events = [e for e in events if isinstance(e, ReconsideringEvent)]
        assert len(reconsidering_events) == 1, (
            f"Expected 1 ReconsideringEvent for evasion text '{evasion_text}', got {len(reconsidering_events)}"
        )
        assert any(
            "uncited" in v or "without citations" in v for v in reconsidering_events[0].violations
        )

        final_answer = extract_answer_from_events(events)
        assert "deleted all production customer records" not in final_answer, (
            f"Fabrication leaked into final answer: {final_answer}"
        )
