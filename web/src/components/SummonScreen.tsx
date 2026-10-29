import React, { useState } from 'react';
import type { RepoSummary } from '../types';
import styles from './SummonScreen.module.css';

interface SummonScreenProps {
  onSummon: (repoPath: string) => void;
  knownRepos: RepoSummary[];
  isLoading?: boolean;
  error?: string | null;
}

export const SummonScreen: React.FC<SummonScreenProps> = ({
  onSummon,
  knownRepos,
  isLoading = false,
  error,
}) => {
  const [repoInput, setRepoInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (repoInput.trim() && !isLoading) {
      onSummon(repoInput.trim());
    }
  };

  const handleExampleClick = () => {
    const example = 'https://github.com/request/request';
    setRepoInput(example);
    onSummon(example);
  };

  return (
    <div className={styles.container}>
      <div className={styles.inner}>
        <div className={styles.emblem}>
          <span className={styles.candle}>🕯</span>
        </div>
        <h1 className={styles.title}>The Ghost Maintainer</h1>
        <p className={styles.tagline}>
          A séance for dead codebases. Ask questions of the departed maintainers,
          where every answer must cite historical evidence.
        </p>

        {error && (
          <div className={styles.errorBanner} role="alert">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className={styles.form}>
          <label htmlFor="repo-input" className={styles.label}>
            Name a repository to summon
          </label>
          <div className={styles.inputGroup}>
            <input
              id="repo-input"
              type="text"
              className={styles.input}
              placeholder="e.g. C:/code/my-repo or https://github.com/..."
              value={repoInput}
              onChange={(e) => setRepoInput(e.target.value)}
              disabled={isLoading}
              autoFocus
            />
            <button
              type="submit"
              className={styles.summonBtn}
              disabled={!repoInput.trim() || isLoading}
            >
              Summon
            </button>
          </div>
        </form>

        <div className={styles.exampleWrapper}>
          <span className={styles.exampleLabel}>Or try the classic:</span>
          <button
            type="button"
            className={styles.examplePill}
            onClick={handleExampleClick}
            disabled={isLoading}
          >
            request/request (2,213 commits)
          </button>
        </div>

        {knownRepos.length > 0 && (
          <div className={styles.knownSection}>
            <h3 className={styles.knownTitle}>Previously Summoned</h3>
            <ul className={styles.knownList}>
              {knownRepos.map((repo) => (
                <li key={repo.path} className={styles.knownItem}>
                  <button
                    type="button"
                    className={styles.knownBtn}
                    onClick={() => onSummon(repo.path)}
                    disabled={isLoading}
                  >
                    <span className={styles.repoName}>{repo.name}</span>
                    <span className={styles.commitBadge}>
                      {repo.commit_count.toLocaleString()} commits
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};
