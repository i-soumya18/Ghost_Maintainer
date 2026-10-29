import React, { useState } from 'react';
import type { RepoSummary } from '../types';
import { Wick } from './Wick';
import { Gallery } from './Gallery';
import { playFlameWhoosh } from '../lib/sound';
import styles from './SummonScreen.module.css';

interface SummonScreenProps {
  onSummon: (repoPath: string, autoQuestion?: string) => void;
  knownRepos: RepoSummary[];
  isLoading?: boolean;
  error?: string | null;
  replayMode?: boolean;
  onOpenLieDetector?: () => void;
}

export const SummonScreen: React.FC<SummonScreenProps> = ({
  onSummon,
  knownRepos,
  isLoading = false,
  error,
  replayMode = false,
  onOpenLieDetector,
}) => {
  const [repoInput, setRepoInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (repoInput.trim() && !isLoading) {
      playFlameWhoosh();
      onSummon(repoInput.trim());
    }
  };

  const handleExampleClick = () => {
    const example = 'https://github.com/request/request';
    setRepoInput(example);
    playFlameWhoosh();
    onSummon(example);
  };

  return (
    <div className={styles.container}>
      <div className={styles.inner}>
        <div className={styles.emblem}>
          <Wick mood="idle" size={96} label="Wick, the Ghost Maintainer mascot" />
        </div>

        <h1 className={styles.title}>The Ghost Maintainer</h1>
        <p className={styles.tagline}>
          A séance for dead codebases. Ask questions of departed maintainers,
          where every factual claim must cite a real, verified git commit hash.
        </p>

        {/* Honesty Benchmark Credibility Strip */}
        <div className={styles.honestyStrip}>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>RAW 4B MODEL</span>
            <span className={styles.statValueBad}>28.6% Fake Citations</span>
            <span className={styles.statSub}>Hallucinates non-existent hashes</span>
          </div>

          <div className={styles.vsDivider}>VS</div>

          <div className={styles.statItem}>
            <span className={styles.statLabel}>GUARDED PIPELINE</span>
            <span className={styles.statValueGood}>100% Real Commits</span>
            <span className={styles.statSub}>Peeled via git cat-file -e</span>
          </div>

          {onOpenLieDetector && (
            <button
              type="button"
              className={styles.lieDetectorPill}
              onClick={onOpenLieDetector}
              title="See side-by-side comparison of caught model hallucinations"
            >
              ⚡ Open Lie Detector
            </button>
          )}
        </div>

        {error && (
          <div className={styles.errorBanner} role="alert">
            {error}
          </div>
        )}

        {!replayMode && (
          <form onSubmit={handleSubmit} className={styles.form}>
            <label htmlFor="repo-input" className={styles.label}>
              Summon any local or remote git repository
            </label>
            <div className={styles.inputGroup}>
              <input
                id="repo-input"
                type="text"
                className={styles.input}
                placeholder="e.g. C:/code/my-repo or https://github.com/owner/repo"
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
        )}

        {!replayMode && (
          <div className={styles.exampleWrapper}>
            <span className={styles.exampleLabel}>Or quick-summon:</span>
            <button
              type="button"
              className={styles.examplePill}
              onClick={handleExampleClick}
              disabled={isLoading}
            >
              request/request (730 commits)
            </button>
          </div>
        )}

        {knownRepos.length > 0 && !replayMode && (
          <div className={styles.knownSection}>
            <h3 className={styles.knownTitle}>Previously Summoned</h3>
            <ul className={styles.knownList}>
              {knownRepos.map((repo) => (
                <li key={repo.path} className={styles.knownItem}>
                  <button
                    type="button"
                    className={styles.knownBtn}
                    onClick={() => {
                      playFlameWhoosh();
                      onSummon(repo.path);
                    }}
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

        {/* Cemetery / Gallery of Dead Repositories */}
        <Gallery onSelectRepo={onSummon} isLoading={isLoading} />
      </div>
    </div>
  );
};
