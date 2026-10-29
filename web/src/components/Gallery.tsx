import React, { useState, useEffect } from 'react';
import { Wick } from './Wick';
import { playFlameWhoosh, playGlassTick } from '../lib/sound';
import styles from './Gallery.module.css';

export interface GalleryRepository {
  id: string;
  name: string;
  years: string;
  status: string;
  commitCount: number;
  stars: string;
  epitaph: string;
  curatedQuestions: string[];
  trapQuestion: {
    question: string;
    explanation: string;
  };
}

interface GalleryProps {
  onSelectRepo: (repoPath: string, autoQuestion?: string) => void;
  isLoading?: boolean;
}

export const Gallery: React.FC<GalleryProps> = ({ onSelectRepo, isLoading = false }) => {
  const [repos, setRepos] = useState<GalleryRepository[]>([]);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    fetch('/gallery.json')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.statusText))))
      .then((data) => setRepos(data.repositories || []))
      .catch(() => {});
  }, []);

  const filtered = repos.filter(
    (r) =>
      r.name.toLowerCase().includes(filter.toLowerCase()) ||
      r.epitaph.toLowerCase().includes(filter.toLowerCase())
  );

  const handleSummon = (repoId: string, question?: string) => {
    playFlameWhoosh();
    onSelectRepo(repoId, question);
  };

  return (
    <section className={styles.galleryContainer} aria-label="Cemetery of Departed Repositories">
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <Wick mood="listening" size={44} />
          <div>
            <h2 className={styles.title}>The Open Source Graveyard</h2>
            <p className={styles.subtitle}>
              Legendary projects that shaped software history before falling silent.
              Hold a séance to question their departed maintainers.
            </p>
          </div>
        </div>

        <div className={styles.searchBox}>
          <input
            type="search"
            className={styles.searchInput}
            placeholder="Search cemetery archives..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Filter graveyard repositories"
          />
        </div>
      </div>

      <div className={styles.grid}>
        {filtered.map((repo) => (
          <article key={repo.id} className={styles.tombstoneCard}>
            <div className={styles.cardHeader}>
              <div className={styles.repoMeta}>
                <span className={styles.statusBadge}>{repo.status}</span>
                <span className={styles.yearsBadge}>{repo.years}</span>
              </div>
              <h3 className={styles.repoName}>{repo.name}</h3>
              <div className={styles.statsRow}>
                <span>★ {repo.stars}</span>
                <span>•</span>
                <span>{repo.commitCount.toLocaleString()} commits</span>
              </div>
            </div>

            <p className={styles.epitaph}>{repo.epitaph}</p>

            <div className={styles.inquiriesSection}>
              <h4 className={styles.inquiriesTitle}>Historical Inquiries:</h4>
              <ul className={styles.questionList}>
                {repo.curatedQuestions.map((q, idx) => (
                  <li key={idx}>
                    <button
                      type="button"
                      className={styles.questionBtn}
                      onClick={() => handleSummon(repo.id, q)}
                      disabled={isLoading}
                    >
                      <span className={styles.bullet}>🕯</span>
                      <span className={styles.questionText}>"{q}"</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            <div className={styles.trapSection}>
              <div className={styles.trapHeader}>
                <span className={styles.trapTag}>False-Premise Trap:</span>
                <span className={styles.trapInfo} title={repo.trapQuestion.explanation}>
                  ℹ Why test?
                </span>
              </div>
              <button
                type="button"
                className={styles.trapBtn}
                onClick={() => {
                  playGlassTick();
                  handleSummon(repo.id, repo.trapQuestion.question);
                }}
                disabled={isLoading}
                title="Tests Rule 4: If the history doesn't support the claim, the ghost strictly refuses."
              >
                <span className={styles.trapIcon}>⚡</span>
                <span className={styles.trapText}>"{repo.trapQuestion.question}"</span>
              </button>
            </div>

            <div className={styles.cardFooter}>
              <button
                type="button"
                className={styles.summonActionBtn}
                onClick={() => handleSummon(repo.id)}
                disabled={isLoading}
              >
                Summon {repo.name.split('/')[1] || repo.name}
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
};

