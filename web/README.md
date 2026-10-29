# Candlelit Archive Web UI 🕯️

A quiet, tactile web interface for The Ghost Maintainer designed with Apple-grade care and zero Halloween clichés.

---

## 🏛️ Architecture Overview

The web client is built with:
- **Framework**: [React 18](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
- **Bundler**: [Vite 5](https://vitejs.dev/)
- **Styling**: Semantic CSS Modules with OKLCH design tokens ([`tokens.css`](src/styles/tokens.css))
- **Icons & Graphics**: Pure SVG, self-hosted typography (zero runtime third-party CDN dependencies)
- **Streaming**: Server-Sent Events (SSE) reader via native `fetch` and `ReadableStream`

---

## 🎨 Design Philosophy & OKLCH Tokens

Follows the aesthetic outlined in [`docs/design.md`](../docs/design.md):
- **Ink and Candle**: Near-black ink background (`--color-bg`) illuminated by warm candle-amber accents (`--color-accent`).
- **Dual Typographic Voice**:
  - `Fraunces` variable serif for the intimate voice of departed maintainers.
  - `JetBrains Mono` for verifiable evidence tags and commit hashes.
  - `Inter` for clean, accessible navigation controls.
- **Redundant Visual Cues**: Verified citations pair amber seals (`✓`) with high-contrast text; unverified or uncited claims display cold chips with dashed underlines and descriptive labels, ensuring full accessibility for color-blind users.

---

## 🧩 Component Hierarchy

```
App.tsx
├── TopBar.tsx (Repository name, commit count, session status)
├── SummonScreen.tsx (Initial ingestion form, recent repos, suggested queries)
├── SeanceScreen.tsx (Interactive séance dialogue)
│   ├── VoiceMessage.tsx (Ghost voice responses, citation chips, status badges)
│   │   ├── CitationChip.tsx (Interactive citation chips with hover highlighting)
│   │   └── ReconsideringIndicator.tsx ("The spirits reconsider..." retry state)
│   ├── RefusalMessage.tsx ("The dead do not remember." refusal state)
│   └── EvidenceRail.tsx (Collapsible right-hand evidence drawer)
│       └── CommitCard.tsx (Commit metadata, author, score, diff hunk previews)
└── CommitDrawer.tsx (Full commit inspector drawer)
```

---

## 🛠️ Development & Build Commands

All commands should be executed from the `web` directory:

```bash
# Install dependencies
npm ci

# Start local Vite development server (hot reload)
npm run dev

# Run ESLint check
npm run lint

# Build production bundle into web/dist
npm run build

# Run frontend unit & SSE resilience test suite
npm test
```

When building for production, `npm run build` compiles static assets into `web/dist/`, which is automatically served by `ghost serve` on `http://127.0.0.1:6660/`.
