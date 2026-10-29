import React, { useMemo } from 'react';
import type { Message, CitationStatus } from '../types';
import { CitationChip } from './CitationChip';
import { RefusalMessage } from './RefusalMessage';
import { ReconsideringIndicator } from './ReconsideringIndicator';
import styles from './VoiceMessage.module.css';

interface VoiceMessageProps {
  message: Message;
  highlightedSha?: string | null;
  onHoverSha?: (sha: string | null) => void;
  onClickSha?: (sha: string) => void;
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

  return (
    <div className={`${styles.bubbleWrapper} ${(styles as Record<string, string>)[role] || ''}`}>
      {role === 'assistant' && (
        <div className={styles.voiceLabel}>
          <span className={styles.ghostGlyph}>🕯</span> The Departed
        </div>
      )}

      {reconsidering && <ReconsideringIndicator reason={reconsidering.reason} />}

      <div className={styles.bubble}>
        {content}

        {role === 'assistant' && !isSilence && (
          <footer className={styles.disclaimer}>
            <span>Voices are fiction.</span> <strong>Evidence is real.</strong>
          </footer>
        )}
      </div>
    </div>
  );
};
