import React from 'react';
import type { Evidence } from '../types';
import styles from './CommitCard.module.css';

interface CommitCardProps {
  evidence: Evidence;
  isHighlighted?: boolean;
  onHover?: (sha: string | null) => void;
  onClick?: (sha: string) => void;
}

export const CommitCard: React.FC<CommitCardProps> = ({
  evidence,
  isHighlighted = false,
  onHover,
  onClick,
}) => {
  const { commit, snippet, relevance_score } = evidence;
  const shortSha = commit.short_sha || commit.sha.slice(0, 7);
  const formattedDate = commit.date ? commit.date.slice(0, 10) : '';

  return (
    <article
      id={`evidence-${shortSha}`}
      className={`${styles.card} ${isHighlighted ? styles.highlighted : ''}`}
      onMouseEnter={() => onHover?.(shortSha)}
      onMouseLeave={() => onHover?.(null)}
      onClick={() => onClick?.(shortSha)}
      tabIndex={0}
      onFocus={() => onHover?.(shortSha)}
      onBlur={() => onHover?.(null)}
      aria-label={`Evidence commit ${shortSha} by ${commit.author}`}
    >
      <header className={styles.header}>
        <div className={styles.tagGroup}>
          <span className={styles.shaChip}>{shortSha}</span>
          {relevance_score !== undefined && (
            <span className={styles.score} title="BM25 relevance score">
              {relevance_score.toFixed(1)}
            </span>
          )}
        </div>
        <div className={styles.meta}>
          <span className={styles.date}>{formattedDate}</span>
          <span className={styles.author}>{commit.author}</span>
        </div>
      </header>

      <h4 className={styles.subject}>{commit.message}</h4>

      {snippet && (
        <p className={styles.snippet}>
          {snippet.length > 220 ? `${snippet.slice(0, 220)}…` : snippet}
        </p>
      )}

      {commit.files_changed && commit.files_changed.length > 0 && (
        <div className={styles.files}>
          {commit.files_changed.slice(0, 3).map((file) => (
            <span key={file} className={styles.fileTag} title={file}>
              {file.split('/').pop()}
            </span>
          ))}
          {commit.files_changed.length > 3 && (
            <span className={styles.fileMore}>
              +{commit.files_changed.length - 3} more
            </span>
          )}
        </div>
      )}
    </article>
  );
};
