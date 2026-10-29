import React from 'react';
import styles from './ReconsideringIndicator.module.css';

interface ReconsideringIndicatorProps {
  reason?: string;
  violations?: string[];
}

export const ReconsideringIndicator: React.FC<ReconsideringIndicatorProps> = ({
  reason = 'The spirits reconsider…',
  violations = [],
}) => {
  return (
    <div className={styles.container} role="status" aria-live="polite">
      <div className={styles.indicator}>
        <span className={styles.candle}>🕯</span>
        <span className={styles.text}>{reason}</span>
      </div>
      {violations.length > 0 && (
        <p className={styles.detail}>
          Citations failed grounding check. Retrying with historical constraints…
        </p>
      )}
    </div>
  );
};
