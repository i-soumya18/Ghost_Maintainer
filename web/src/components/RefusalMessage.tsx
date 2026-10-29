import React from 'react';
import styles from './RefusalMessage.module.css';

export const RefusalMessage: React.FC = () => {
  return (
    <div className={styles.container} role="status">
      <div className={styles.line}>The dead do not remember.</div>
      <div className={styles.subline}>
        No commit speaks to this. Try naming a specific file, author, or feature.
      </div>
    </div>
  );
};
