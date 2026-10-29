import React from 'react';
import type { RepoInfo } from '../types';
import styles from './TopBar.module.css';

interface TopBarProps {
  repo: RepoInfo | null;
  onChangeRepo?: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({ repo, onChangeRepo }) => {
  return (
    <header className={styles.topbar} role="banner">
      <div className={styles.inner}>
        <div className={styles.brand}>
          <span className={styles.brandGlyph} aria-hidden="true">◉</span>
          <span className={styles.brandName}>Ghost Maintainer</span>
        </div>
        {repo && (
          <div className={styles.repoInfo}>
            <span className={styles.repoPath} title={repo.path}>
              {repo.name}
            </span>
            <span
              className={styles.commitCount}
              aria-label={`${repo.commitCount.toLocaleString()} commits indexed`}
            >
              {repo.commitCount.toLocaleString()} commits
            </span>
          </div>
        )}
        {repo && onChangeRepo && (
          <button
            type="button"
            className={styles.changeBtn}
            onClick={onChangeRepo}
            aria-label="Summon a different repository"
          >
            Summon other
          </button>
        )}
      </div>
    </header>
  );
};
