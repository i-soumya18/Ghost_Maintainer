# Candlelit Archive: Design System & UX Architecture

The Ghost Maintainer web interface was engineered following the principles of [`apple-grade-design`](https://developer.apple.com/design/human-interface-guidelines/).

The guiding metaphor is:
> **A quiet archive at midnight, lit by candlelight, not a laser show.**

We deliberately avoided novelty Halloween aesthetics—no neon greens, no animated cartoon skulls, no jarring sound effects. The interface feels scholarly, respectful, tactile, and quiet.

---

## 1. Perceptually Uniform Color Palette (OKLCH)

We use the **OKLCH** color model to guarantee predictable lightness contrasts across displays and dark ambient settings:

| Token Name | OKLCH Value | Semantic Role |
| :--- | :--- | :--- |
| `--bg-base` | `oklch(0.14 0.012 55)` | Deep archival obsidian background |
| `--bg-surface` | `oklch(0.18 0.016 60)` | Elevated drawer, rail, and card surfaces |
| `--bg-surface-raised` | `oklch(0.22 0.020 65)` | Popovers, active citation cards |
| `--border-subtle` | `oklch(0.28 0.018 60)` | Hairline dividers and grid lines |
| `--text-primary` | `oklch(0.96 0.008 80)` | Ghost voice narrative and headings |
| `--text-secondary` | `oklch(0.74 0.012 75)` | Commit metadata, diff lines, author names |
| `--text-muted` | `oklch(0.52 0.010 70)` | Timestamps, file paths, disclaimers |
| `--accent-amber` | `oklch(0.78 0.160 75)` | Verified citations, focus rings, primary actions |
| `--accent-amber-glow` | `oklch(0.78 0.160 75 / 0.15)` | Soft ambient glow for active elements |
| `--status-verified` | `oklch(0.72 0.140 145)` | Muted sage green for grounded assertions |
| `--status-refused` | `oklch(0.65 0.020 60)` | Ash gray for "The dead do not remember" |
| `--status-warning` | `oklch(0.70 0.160 50)` | Muted terracotta for self-correction alerts |

---

## 2. Typography

The typographic hierarchy balances literary gravitas with archaeological precision:

- **Ghost Voice Narrative**: `Fraunces`
  - Variable serif font with soft optical sizing.
  - Used for ghost answers to convey the intimate, reflective collective voice of past maintainers.
- **Interface & Metadata**: `Inter`
  - Ultra-legible neutral sans-serif for UI labels, drawer headers, and commit cards.
- **Commit Hashes & Code**: `JetBrains Mono`
  - Fixed-width font with tabular figures for 7-character commit hashes, unified diffs, and CLI logs.

---

## 3. The 10 Designed States

A robust, delightful UX accounts for every transition. Ghost Maintainer implements 10 explicit states:

1. **Idle Summon**: Clean hero asking for a local repository path or selecting from previously indexed repos.
2. **Indexing Progress**: Real-time progress bar showing commits processed, elapsed time, and BM25 index status.
3. **Query Composer**: Input field with hotkey hints (`Enter` to submit, example historical questions).
4. **Evidence Rail**: Expandable side rail listing top-ranked BM25 commit evidence with scores.
5. **Streaming Tokens**: SSE stream typing out tokens smoothly with soft amber cursor glow.
6. **Reconsidering Indicator**: Gentle banner showing the model detected an ungrounded citation and is executing self-correction.
7. **Verified Response**: Formatted ghost narrative with interactive, clickable `CitationChip` components.
8. **Ungrounded Warning**: Subtle notice when citations were stripped because the repository had no matching diff evidence.
9. **Dead Refusal**: Dignified quiet typography rendering *"The dead do not remember."* when query falls below retrieval gate.
10. **System Diagnostics**: Detailed drawer showing backend status, GPU VRAM usage, and git execution times.

---

## 4. Accessibility & Apple HIG Standards (WCAG AA)

- **Contrast Ratios**: All text tokens maintain minimum $4.5:1$ contrast against their respective backgrounds ($7:1$ for primary narrative).
- **Keyboard Traversal**:
  - `Tab` cycles through questions, citation chips, and evidence cards.
  - `Enter` / `Space` opens commit details in the drawer.
  - `Escape` closes overlays and drawers.
  - Explicit high-contrast focus rings (`outline: 2px solid var(--accent-amber)` with offset).
- **Screen Reader Announcements**:
  - `aria-live="polite"` regions inform screen readers of streaming tokens without overwhelming the user.
  - Refusals and errors emit clear alerts.
- **Reduced Motion**:
  - `@media (prefers-reduced-motion: reduce)` disables pulse animations and smooth drawer slides, providing instant state transitions.
