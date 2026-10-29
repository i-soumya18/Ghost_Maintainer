# Candlelit Archive: Design System & UX Architecture

The Ghost Maintainer web interface was engineered following the principles of [`apple-grade-design`](https://developer.apple.com/design/human-interface-guidelines/).

The guiding metaphor is:
> **A tactile midnight archive lit by candlelight, with scholarly gravitas and playful occult craft.**

The design balances academic dignity with delightful virality:
- Deep obsidian and warm amber parchment tones.
- Original vector artwork mascot (**Wick**, the candle-flame spirit) replacing novelty emojis.
- Zero external audio files: WebAudio-synthesized atmospheric audio cues (flame whoosh, glass-tick, sub-thud).
- Cryptographic and archaeological evidence surfaced in high-density, interactive views.

---

## 1. Perceptually Uniform Color Palette (OKLCH)

We use the **OKLCH** color model to guarantee predictable lightness contrasts across displays and dark ambient settings:

| Token Name | OKLCH Value | Semantic Role |
| :--- | :--- | :--- |
| `--color-bg` | `oklch(14% 0.01 60)` | Deep archival obsidian background |
| `--color-surface` | `oklch(18% 0.012 60)` | Elevated drawer, rail, and card surfaces |
| `--color-surface-2` | `oklch(22% 0.013 60)` | Hover states, tab containers, secondary cards |
| `--color-border` | `oklch(28% 0.01 60)` | Hairline dividers and grid lines |
| `--color-text` | `oklch(92% 0.01 80)` | Ghost voice narrative and primary headings |
| `--color-text-muted` | `oklch(70% 0.01 80)` | Commit metadata, diff lines, author names |
| `--color-text-dim` | `oklch(52% 0.01 80)` | Timestamps, file paths, disclaimers |
| `--color-accent` | `oklch(78% 0.14 70)` | Warm candlelight amber: verified citations, primary actions |
| `--color-spirit` | `oklch(82% 0.13 195)` | Ethereal cyan spirit: Wick mascot glow, Citation Constellation |
| `--color-lie` | `oklch(66% 0.22 25)` | Flaming terracotta red: caught AI hallucinations and strikethroughs |
| `--color-tombstone` | `oklch(26% 0.012 60)` | Granite gray: graveyard tombstones and cemetery epitaphs |

---

## 2. Typography

The typographic hierarchy balances literary gravitas with archaeological precision:

- **Ghost Voice Narrative**: `Fraunces`
  - Variable serif font with soft optical sizing.
  - Used for ghost answers to convey the intimate, reflective collective voice of past maintainers.
- **Interface & Metadata**: `Inter`
  - Ultra-legible neutral sans-serif for UI labels, tab navigation, and action buttons.
- **Commit Hashes & Code**: `JetBrains Mono`
  - Fixed-width font with tabular figures for 7-character commit hashes, unified diffs, and CLI logs.

---

## 3. Mascot: Wick, The Candle-Flame Spirit

Wick is an original SVG vector entity with zero external dependencies. Wick reacts dynamically to pipeline states:

| Mood | Visual Behavior | Trigger State |
| :--- | :--- | :--- |
| `idle` | Gentle vertical float, flame sway | Resting, waiting for inquiry |
| `listening` | Eyes dilate, flame leans forward | Retrieving BM25 evidence |
| `speaking` | Animated mouth, warm flickering aura | Streaming tokens from model |
| `reconsidering` | Slight wobble, pursed mouth | Verifier caught violation; self-correcting |
| `silent` | Closed peaceful eyes, dimmed flame wisp | Refusal: "The dead do not remember." |

---

## 4. The 4 Archaeological Views

1. **The Séance Room**
   - Clean chat interface with Fraunces serif ghost voice.
   - Interactive `CitationChip` tags linking to real commit records.
   - Slide-out `CommitDrawer` showing full unified diffs and stat lines.
   - Evidence Rail with `CitationConstellation` connecting cited commits by file changes.

2. **The AI Lie Detector**
   - Side-by-side comparison between Raw 4B Model (unfiltered) and The Guarded Pipeline.
   - Red ink strike-through on fabricated hashes (`[deadbeef] ✗ LIE`).
   - Forensic analysis explaining why the hallucination occurred.
   - Demonstrates the 100% Citation Existence Rate and Refusal Recall.

3. **The Graveyard Timeline**
   - Stratigraphic commit density histogram over the repository's lifetime.
   - Tombstone of Inactivity: exact date and subject of the final commit, plus days of silence.
   - Departed maintainers leaderboard with commit counts.
   - Historical era jump buttons.

4. **The Cemetery Gallery**
   - Tombstone cards for famous deprecated projects (`request`, `bower`, `atom`, `backbone`).
   - Historical cause-of-death epitaphs.
   - 3 curated questions per project + 1 intentional False-Premise Trap.

---

## 5. WebAudio Synthesized Sound Design

To respect developer environments, sound is **off by default** and toggled via the TopBar.
All sounds are mathematically synthesized via the WebAudio API:
- `playFlameWhoosh()`: Filtered white noise burst on repository summon.
- `playGlassTick()`: 1480Hz pure sine chime when a citation verifies against git.
- `playLieThud()`: 110Hz -> 42Hz triangle sub-thud when an AI hallucination is struck.
- `playEerieChime()`: E-major harmonic chord triad when the ghost speaks.
- `playGhostChoir()`: 4-chord minor progression for the Konami code easter egg.

---

## 6. Accessibility & Apple HIG Standards (WCAG AA)

- **Contrast Ratios**: Minimum 4.5:1 for UI labels; 7:1 for Fraunces ghost voice against deep obsidian.
- **Keyboard Navigation**: Full Tab/Shift-Tab cycling through chips and cards; Escape closes modal and drawer.
- **Reduced Motion**: All animations (flame sway, float, pulse) collapse to 0ms when `prefers-reduced-motion` is detected.
- **Screen Readers**: `aria-live="polite"` regions stream tokens without interrupting user focus.
