import React from 'react';
import { Wick } from './Wick';
import styles from './IndexingProgress.module.css';

interface IndexingProgressProps {
  processed: number;
  total: number;
  phaseName?: string;
  repoName?: string;
}

export const IndexingProgress: React.FC<IndexingProgressProps> = ({
  processed,
  total,
  phaseName = 'Gathering memories\u2026',
  repoName = 'repository',
}) => {
  const percentage = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;

  return (
    <div
      className={styles.container}
      role="progressbar"
      aria-valuenow={percentage}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Indexing ${repoName}`}
    >
      <div className={styles.candleIcon}>
        <Wick mood="listening" size={72} />
      </div>
      <h2 className={styles.title}>{phaseName}</h2>
      <p className={styles.subtitle}>
        Examining commit logs, hunk context, and file histories for{' '}
        <strong>{repoName}</strong>.
      </p>
      <div className={styles.progressTrack}>
        <div className={styles.progressBar} style={{ width: `${percentage}%` }} />
      </div>
      <div className={styles.counts}>
        <span>
          {total > 0
            ? `Step ${Math.min(processed + 1, total)} of ${total}`
            : 'Analyzing repository structure\u2026'}
        </span>
        {total > 0 && <span>{percentage}%</span>}
      </div>
    </div>
  );
};
