import React from 'react';
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
  phaseName = 'Gathering memories…',
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
    >
      <div className={styles.candleIcon}>🕯</div>
      <h2 className={styles.title}>{phaseName}</h2>
      <p className={styles.subtitle}>
        Examining commit logs, hunk context, and file histories for{' '}
        <strong>{repoName}</strong>.
      </p>
      <div className={styles.progressTrack}>
        <div
          className={styles.progressBar}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <div className={styles.counts}>
        <span>
          {processed > 0 && total > 0
            ? `${processed.toLocaleString()} of ${total.toLocaleString()} commits`
            : 'Analyzing repository structure…'}
        </span>
        {total > 0 && <span>{percentage}%</span>}
      </div>
    </div>
  );
};
