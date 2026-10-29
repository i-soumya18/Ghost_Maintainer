import React from 'react';
import type { CitationStatus } from '../types';
import styles from './CitationChip.module.css';

interface CitationChipProps {
  sha: string;
  status?: CitationStatus;
  isHighlighted?: boolean;
  onClick?: (sha: string) => void;
  onMouseEnter?: (sha: string) => void;
  onMouseLeave?: () => void;
}

export const CitationChip: React.FC<CitationChipProps> = ({
  sha,
  status = 'pending',
  isHighlighted = false,
  onClick,
  onMouseEnter,
  onMouseLeave,
}) => {
  const shortSha = sha.length > 7 ? sha.slice(0, 7) : sha;
  const label =
    status === 'verified'
      ? `Verified commit ${shortSha}`
      : status === 'unverified'
      ? `Unverified commit ${shortSha}`
      : `Commit citation ${shortSha}`;

  const statusClass = (styles as Record<string, string>)[status] || '';

  return (
    <button
      type="button"
      className={`${styles.chip} ${statusClass} ${isHighlighted ? styles.highlighted : ''}`}
      onClick={() => onClick?.(sha)}
      onMouseEnter={() => onMouseEnter?.(sha)}
      onMouseLeave={onMouseLeave}
      onFocus={() => onMouseEnter?.(sha)}
      onBlur={onMouseLeave}
      aria-label={label}
      title={label}
    >
      <span className={styles.prefix}>[</span>
      <span className={styles.sha}>{shortSha}</span>
      {status === 'verified' && (
        <span className={styles.icon} aria-hidden="true"> ✓</span>
      )}
      {status === 'unverified' && (
        <span className={styles.icon} aria-hidden="true"> ⚠</span>
      )}
      <span className={styles.prefix}>]</span>
    </button>
  );
};
