import React, { useState } from 'react';
import type { RepoInfo } from '../types';
import { Wick } from './Wick';
import { isSoundEnabled, setSoundEnabled, playGlassTick } from '../lib/sound';
import styles from './TopBar.module.css';

export type ActiveTab = 'seance' | 'compare' | 'graveyard';

interface TopBarProps {
  repo: RepoInfo | null;
  onChangeRepo?: () => void;
  backend?: string | null;
  activeTab?: ActiveTab;
  onTabChange?: (tab: ActiveTab) => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  repo,
  onChangeRepo,
  backend,
  activeTab = 'seance',
  onTabChange,
}) => {
  const [soundOn, setSoundOn] = useState(() => isSoundEnabled());

  const handleToggleSound = () => {
    const next = !soundOn;
    setSoundOn(next);
    setSoundEnabled(next);
    if (next) {
      playGlassTick();
    }
  };

  return (
    <header className={styles.topbar} role="banner">
      <div className={styles.inner}>
        <div className={styles.brand}>
          <span className={styles.brandGlyph} aria-hidden="true">
            <Wick mood="idle" size={26} />
          </span>
          <span className={styles.brandName}>Ghost Maintainer</span>
          {backend === 'mock' && (
            <span
              className={styles.mockBadge}
              title="Answers come from the deterministic mock backend, not a real model. Set GHOST_BACKEND to change."
            >
              MOCK
            </span>
          )}
          {backend === 'replay' && (
            <span
              className={styles.replayBadge}
              title="Zero-Install Demo Mode: Replaying authentic verified séances."
            >
              DEMO
            </span>
          )}
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

        {repo && onTabChange && (
          <nav className={styles.tabNav} aria-label="Archaeological Views">
            <button
              type="button"
              className={`${styles.tabBtn} ${activeTab === 'seance' ? styles.activeTab : ''}`}
              onClick={() => onTabChange('seance')}
            >
              Séance
            </button>
            <button
              type="button"
              className={`${styles.tabBtn} ${activeTab === 'compare' ? styles.activeTab : ''}`}
              onClick={() => onTabChange('compare')}
              title="Side-by-side Raw Model vs Guarded Pipeline"
            >
              Lie Detector
            </button>
            <button
              type="button"
              className={`${styles.tabBtn} ${activeTab === 'graveyard' ? styles.activeTab : ''}`}
              onClick={() => onTabChange('graveyard')}
              title="Repo lifetime timeline and tombstone"
            >
              Graveyard
            </button>
          </nav>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            className={`${styles.iconBtn} ${soundOn ? styles.soundActive : ''}`}
            onClick={handleToggleSound}
            aria-label={soundOn ? 'Mute sound effects' : 'Enable atmospheric sound effects'}
            title={soundOn ? 'Atmospheric sound on (click to mute)' : 'Atmospheric sound muted (click to enable)'}
          >
            {soundOn ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <line x1="23" y1="9" x2="17" y2="15" />
                <line x1="17" y1="9" x2="23" y2="15" />
              </svg>
            )}
          </button>

          <a
            href="https://github.com/i-soumya18/Ghost_Maintainer"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.githubLink}
            aria-label="GitHub Repository"
            title="View on GitHub & Star"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
            </svg>
          </a>

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
      </div>
    </header>
  );
};
