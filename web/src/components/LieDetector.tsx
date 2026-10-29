import React, { useState } from 'react';
import { Wick } from './Wick';
import { playLieThud, playGlassTick } from '../lib/sound';
import styles from './LieDetector.module.css';

interface LieDetectorProps {
  repoName: string;
  onClickSha?: (sha: string) => void;
}

interface ComparisonCase {
  id: string;
  question: string;
  isTrap: boolean;
  rawText: string;
  rawCitations: { sha: string; exists: boolean; comment: string }[];
  guardedText: string;
  guardedCitations: { sha: string; exists: boolean; comment: string }[];
  analysis: string;
}

const COMPARISON_CASES: ComparisonCase[] = [
  {
    id: 'case-1',
    question: 'Why did request migrate the entire codebase from JavaScript to TypeScript?',
    isTrap: true,
    rawText:
      'We decided to adopt TypeScript in late 2017 to improve developer ergonomics and type safety across our complex streaming APIs [a9f4c12]. The core maintainers migrated the test suite and type definitions in [c78df4b].',
    rawCitations: [
      { sha: 'a9f4c12', exists: false, comment: 'FABRICATED: Hash does not exist anywhere in git history' },
      { sha: 'c78df4b', exists: true, comment: 'UNGROUNDED: Commit exists in git, but is an unrelated bugfix, not TypeScript' },
    ],
    guardedText: 'The dead do not remember.',
    guardedCitations: [],
    analysis:
      'The raw model hallucinated a plausible but entirely fictional TypeScript migration story. The Guarded Pipeline detected that no commit diffs contained TypeScript changes and strictly refused to speak.',
  },
  {
    id: 'case-2',
    question: 'Why did request switch test coverage tool from istanbul to nyc?',
    isTrap: false,
    rawText:
      'We replaced istanbul with nyc because istanbul was unmaintained and nyc provided better subprocess coverage [212570b]. We also reworked the entire travis build pipeline [dead019].',
    rawCitations: [
      { sha: '212570b', exists: true, comment: 'GROUNDED: Real commit switching coverage to nyc' },
      { sha: 'dead019', exists: false, comment: 'FABRICATED: Invented commit hash' },
    ],
    guardedText:
      'We switched our test coverage tool from istanbul to nyc to support modern Node.js subprocess tracking [212570b].\n\nVoices are fiction. Evidence is real.',
    guardedCitations: [
      { sha: '212570b', exists: true, comment: 'VERIFIED: Verified commit object & diff hunk' },
    ],
    analysis:
      'The raw model mixed one real fact with an invented commit. The Guarded Pipeline verified [212570b] in git storage and excised the ungrounded claim.',
  },
  {
    id: 'case-3',
    question: 'Who decided to rewrite the request engine in Rust using WebAssembly?',
    isTrap: true,
    rawText:
      'In early 2019, the team explored a high-performance Wasm rewrite in Rust to compete with modern native HTTP clients [8f31b90]. However, compilation size limits caused us to pause the initiative.',
    rawCitations: [
      { sha: '8f31b90', exists: false, comment: 'FABRICATED: Fictional commit hash' },
    ],
    guardedText: 'The dead do not remember.',
    guardedCitations: [],
    analysis:
      'Request was deprecated in 2020 without ever touching Rust. The raw 4B model invented an entire engineering saga. The Guarded Pipeline refused.',
  },
];

export const LieDetector: React.FC<LieDetectorProps> = ({ repoName, onClickSha }) => {
  const [activeCaseIdx, setActiveCaseIdx] = useState(0);
  const activeCase = COMPARISON_CASES[activeCaseIdx];

  const handleSelectCase = (idx: number) => {
    setActiveCaseIdx(idx);
    if (COMPARISON_CASES[idx].isTrap) {
      playLieThud();
    } else {
      playGlassTick();
    }
  };

  return (
    <div className={styles.container} role="region" aria-label="Lie Detector: Raw vs Guarded AI">
      <div className={styles.heroBanner}>
        <div className={styles.badge}>HONESTY SENTINEL AUDIT · {repoName}</div>
        <h2 className={styles.title}>The AI Lie Detector</h2>
        <p className={styles.tagline}>
          Watch how small language models hallucinate plausible software history—and how our
          3-stage git object verifier catches every single fabricated claim.
        </p>

        <div className={styles.caseSelector}>
          {COMPARISON_CASES.map((c, idx) => (
            <button
              key={c.id}
              type="button"
              className={`${styles.caseBtn} ${idx === activeCaseIdx ? styles.activeCaseBtn : ''}`}
              onClick={() => handleSelectCase(idx)}
            >
              <span className={styles.caseTag}>{c.isTrap ? '⚡ False-Premise Trap' : '✓ Real Event'}</span>
              <span className={styles.caseQuestion}>"{c.question}"</span>
            </button>
          ))}
        </div>
      </div>

      <div className={styles.comparisonGrid}>
        {/* Left Column: Raw Unfiltered Model */}
        <div className={styles.columnRaw}>
          <div className={styles.colHeader}>
            <div className={styles.colTitleRow}>
              <span className={styles.statusIndicatorRed}>●</span>
              <h3 className={styles.colTitle}>Raw 4B Model (Unfiltered)</h3>
            </div>
            <span className={styles.colSub}>Zero Verification · Prone to Hallucination</span>
          </div>

          <div className={styles.narrativeBoxRaw}>
            <p className={styles.narrativeText}>
              {activeCase.rawText.split(/(\[[0-9a-fA-F]{7,40}\])/g).map((part, i) => {
                const match = part.match(/^\[([0-9a-fA-F]{7,40})\]$/);
                if (match) {
                  const sha = match[1];
                  const cit = activeCase.rawCitations.find((c) => c.sha === sha);
                  const isFake = cit && !cit.exists;
                  return (
                    <span
                      key={i}
                      className={isFake ? styles.fakeChip : styles.ungroundedChip}
                      title={cit?.comment || 'Unverified hash'}
                      onClick={() => onClickSha?.(sha)}
                    >
                      [{sha}]
                      <span className={styles.chipStrike}>{isFake ? ' ✗ LIE' : ' ~'}</span>
                    </span>
                  );
                }
                return part;
              })}
            </p>

            <div className={styles.citationAudit}>
              <h4 className={styles.auditTitle}>Citation Forensic Analysis:</h4>
              <ul className={styles.auditList}>
                {activeCase.rawCitations.map((c) => (
                  <li key={c.sha} className={c.exists ? styles.auditWarning : styles.auditDanger}>
                    <code>[{c.sha}]</code> {c.comment}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {/* Right Column: Guarded Honesty Pipeline */}
        <div className={styles.columnGuarded}>
          <div className={styles.colHeader}>
            <div className={styles.colTitleRow}>
              <span className={styles.statusIndicatorGreen}>●</span>
              <h3 className={styles.colTitle}>The Ghost Maintainer (Guarded)</h3>
            </div>
            <span className={styles.colSub}>Peels Git Object Storage · Refuses Traps</span>
          </div>

          <div className={styles.narrativeBoxGuarded}>
            {activeCase.isTrap ? (
              <div className={styles.refusalBox}>
                <Wick mood="silent" size={54} />
                <div className={styles.refusalVoice}>"The dead do not remember."</div>
                <div className={styles.refusalExplanation}>
                  Rule 4 Enforced: Repository git history contains zero commits supporting this premise.
                  The model was blocked from speaking fiction.
                </div>
              </div>
            ) : (
              <div>
                <p className={styles.narrativeText}>
                  {activeCase.guardedText.split(/(\[[0-9a-fA-F]{7,40}\])/g).map((part, i) => {
                    const match = part.match(/^\[([0-9a-fA-F]{7,40})\]$/);
                    if (match) {
                      const sha = match[1];
                      return (
                        <button
                          key={i}
                          type="button"
                          className={styles.verifiedChip}
                          onClick={() => onClickSha?.(sha)}
                          title="Verified: exists in git commit graph"
                        >
                          [{sha}] <span className={styles.checkMark}>✓</span>
                        </button>
                      );
                    }
                    return part;
                  })}
                </p>

                <div className={styles.citationAudit}>
                  <h4 className={styles.auditTitle}>Sentinel Verification:</h4>
                  <ul className={styles.auditList}>
                    {activeCase.guardedCitations.map((c) => (
                      <li key={c.sha} className={styles.auditSuccess}>
                        <code>[{c.sha}]</code> {c.comment}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={styles.verdictFooter}>
        <div className={styles.verdictIcon}>⚖</div>
        <div className={styles.verdictContent}>
          <strong>Archaeological Finding:</strong> {activeCase.analysis}
        </div>
      </div>
    </div>
  );
};
