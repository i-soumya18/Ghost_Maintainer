import React from 'react';
import { Wick } from './Wick';
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
        <span className={styles.candle}><Wick mood="reconsidering" size={20} /></span>
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
