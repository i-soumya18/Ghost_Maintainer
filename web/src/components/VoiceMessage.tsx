import React, { useMemo } from 'react';
import type { Message, CitationStatus } from '../types';
import { CitationChip } from './CitationChip';
import { RefusalMessage } from './RefusalMessage';
import { ReconsideringIndicator } from './ReconsideringIndicator';
import { Wick } from './Wick';
import styles from './VoiceMessage.module.css';

interface VoiceMessageProps {
  message: Message;
  highlightedSha?: string | null;
  onHoverSha?: (sha: string | null) => void;
  onClickSha?: (sha: string) => void;
  onShareProof?: (message: Message) => void;
  onOpenLieDetector?: () => void;
}

function renderTextWithCitations(
  text: string,
  defaultStatus: CitationStatus,
  highlightedSha?: string | null,
  onHoverSha?: (sha: string | null) => void,
  onClickSha?: (sha: string) => void
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const citationRegex = /\[([0-9a-fA-F]{7,40})\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = citationRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const sha = match[1].toLowerCase();
    const isHighlighted =
      Boolean(highlightedSha) &&
      (highlightedSha === sha || sha.startsWith(highlightedSha!));
    const status: CitationStatus = defaultStatus === 'uncited' ? 'unverified' : defaultStatus;

    parts.push(
      <CitationChip
        key={`${match.index}-${sha}`}
        sha={sha}
        status={status}
        isHighlighted={isHighlighted}
        onMouseEnter={onHoverSha}
        onMouseLeave={() => onHoverSha?.(null)}
        onClick={onClickSha}
      />
    );
    lastIndex = citationRegex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

export const VoiceMessage: React.FC<VoiceMessageProps> = ({
  message,
  highlightedSha,
  onHoverSha,
  onClickSha,
  onShareProof,
  onOpenLieDetector,
}) => {
  const { role, text, streamPhase, verdict, reconsidering } = message;

  const isSilence =
    streamPhase === 'silence' ||
    text.trim() === 'The dead do not remember.' ||
    text.startsWith('The dead do not remember.');

  const content = useMemo(() => {
    if (role === 'user') {
      return <div className={styles.userText}>{text}</div>;
    }

    if (message.error || streamPhase === 'error') {
      return (
        <div className={styles.errorContent} role="alert">
          <div className={styles.errorHeader}>
            <span className={styles.errorIcon}>⚠</span>
            <strong>The séance connection was severed</strong>
          </div>
          <p className={styles.errorText}>
            {message.error || 'The spirits fell silent unexpectedly. Please inquire again.'}
          </p>
        </div>
      );
    }

    if (isSilence) {
      return <RefusalMessage />;
    }

    if (verdict && verdict.sentences && verdict.sentences.length > 0) {
      return (
        <div className={styles.assistantText} aria-live="polite">
          {verdict.sentences.map((sentence, idx) => {
            if (
              sentence.text.includes('Voices are fiction') ||
              sentence.text.includes('Evidence is real')
            ) {
              return null;
            }
            const statusClass = (styles as Record<string, string>)[sentence.status] || '';
            return (
              <span
                key={idx}
                className={`${styles.sentence} ${statusClass}`}
                title={`Sentence status: ${sentence.status}`}
              >
                {renderTextWithCitations(
                  sentence.text,
                  sentence.status,
                  highlightedSha,
                  onHoverSha,
                  onClickSha
                )}{' '}
              </span>
            );
          })}
        </div>
      );
    }

    return (
      <div className={styles.assistantText} aria-live="polite">
        {renderTextWithCitations(
          text,
          'pending',
          highlightedSha,
          onHoverSha,
          onClickSha
        )}
      </div>
    );
  }, [
    role,
    text,
    isSilence,
    verdict,
    highlightedSha,
    onHoverSha,
    onClickSha,
    message.error,
    streamPhase,
  ]);

  const verifiedSentences = verdict?.sentences?.filter((s) => s.status === 'verified').length || 0;
  const totalSentences = verdict?.sentences?.length || 0;

  return (
    <div className={`${styles.bubbleWrapper} ${(styles as Record<string, string>)[role] || ''}`}>
      {role === 'assistant' && (
        <div className={styles.voiceLabel}>
          <span className={styles.ghostGlyph}>
            <Wick
              mood={
                isSilence
                  ? 'silent'
                  : streamPhase === 'reconsidering'
                  ? 'reconsidering'
                  : streamPhase === 'streaming'
                  ? 'speaking'
                  : 'idle'
              }
              size={22}
            />
          </span>{' '}
          The Departed
        </div>
      )}

      {reconsidering && <ReconsideringIndicator reason={reconsidering.reason} />}

      <div className={styles.bubble}>
        {content}

        {role === 'assistant' && !isSilence && streamPhase !== 'streaming' && (
          <div className={styles.messageFooter}>
            <div className={styles.verdictBar}>
              {verdict && totalSentences > 0 ? (
                <span className={styles.verifiedCountBadge}>
                  ✓ {verifiedSentences}/{totalSentences} claims verified against git
                </span>
              ) : (
                <span className={styles.forensicBadge}>Forensically verified</span>
              )}
            </div>

            <div className={styles.actionButtons}>
              {onOpenLieDetector && (
                <button
                  type="button"
                  className={styles.lieDetectorBtn}
                  onClick={onOpenLieDetector}
                  title="Compare with what an unverified raw AI would claim"
                >
                  ⚡ Compare in Lie Detector
                </button>
              )}

              {onShareProof && text.trim() && (
                <button
                  type="button"
                  className={styles.shareProofBtn}
                  onClick={() => onShareProof(message)}
                  title="Generate downloadable 1200x630 proof card"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="18" cy="5" r="3" />
                    <circle cx="6" cy="12" r="3" />
                    <circle cx="18" cy="19" r="3" />
                    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                  </svg>
                  Share Proof
                </button>
              )}
            </div>
          </div>
        )}

        {role === 'assistant' && !isSilence && (
          <footer className={styles.disclaimer}>
            <span>Voices are fiction.</span> <strong>Evidence is real.</strong>
          </footer>
        )}
      </div>
    </div>
  );
};
