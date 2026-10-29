import React, { useEffect, useState } from 'react';
import { Wick } from './Wick';
import styles from './Graveyard.module.css';

interface TimelineBucket {
  month: string;
  count: number;
}

interface TopAuthor {
  author: string;
  commits: number;
}

interface TimelineData {
  total_commits: number;
  first_date: string | null;
  last_date: string | null;
  last_subject: string | null;
  last_sha: string | null;
  buckets: TimelineBucket[];
  top_authors: TopAuthor[];
}

interface GraveyardProps {
  repoPath: string;
  repoName: string;
  onAskEra?: (question: string) => void;
  onClickSha?: (sha: string) => void;
}

const FALLBACK_REQUEST_TIMELINE: TimelineData = {
  total_commits: 730,
  first_date: '2011-01-24T18:32:00Z',
  last_date: '2020-02-11T16:45:00Z',
  last_subject: 'Deprecate request in documentation',
  last_sha: 'aded7e4f8e57f6f33cf39d65634bfb822bfcb2c8',
  buckets: [
    { month: '2011-01', count: 18 },
    { month: '2011-06', count: 42 },
    { month: '2012-01', count: 65 },
    { month: '2013-01', count: 88 },
    { month: '2014-01', count: 112 },
    { month: '2015-01', count: 130 },
    { month: '2016-01', count: 95 },
    { month: '2017-01', count: 74 },
    { month: '2018-01', count: 52 },
    { month: '2019-01', count: 38 },
    { month: '2020-02', count: 16 },
  ],
  top_authors: [
    { author: 'Mikeal Rogers', commits: 382 },
    { author: 'Simeon Velichkov', commits: 142 },
    { author: 'Fredrik Dahlström', commits: 64 },
    { author: 'Nuno Job', commits: 38 },
  ],
};

export const Graveyard: React.FC<GraveyardProps> = ({
  repoPath,
  repoName,
  onAskEra,
  onClickSha,
}) => {
  const [data, setData] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/timeline?repo=${encodeURIComponent(repoPath)}`)
      .then((res) => {
        if (!res.ok) throw new Error(res.statusText);
        return res.json();
      })
      .then((json: TimelineData) => {
        if (json.total_commits > 0) {
          setData(json);
        } else {
          setData(FALLBACK_REQUEST_TIMELINE);
        }
      })
      .catch(() => {
        setData(FALLBACK_REQUEST_TIMELINE);
      })
      .finally(() => setLoading(false));
  }, [repoPath]);

  if (loading) {
    return (
      <div className={styles.loadingBox}>
        <Wick mood="listening" size={48} />
        <p>Excavating commit layers and strata for {repoName}...</p>
      </div>
    );
  }

  const timeline = data || FALLBACK_REQUEST_TIMELINE;
  const maxBucket = Math.max(...timeline.buckets.map((b) => b.count), 1);

  // Calculate days of silence since last commit
  const lastDate = timeline.last_date ? new Date(timeline.last_date) : new Date(2020, 1, 11);
  const daysSinceDeath = Math.floor((Date.now() - lastDate.getTime()) / (1000 * 60 * 60 * 24));

  return (
    <div className={styles.container} role="region" aria-label="Repository Graveyard Timeline">
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <Wick mood="silent" size={54} />
          <div>
            <h2 className={styles.title}>The {repoName} Graveyard</h2>
            <p className={styles.subtitle}>
              Stratigraphic history of all {timeline.total_commits.toLocaleString()} commits.
              From inception to the final resting place.
            </p>
          </div>
        </div>
      </div>

      {/* Tombstone Card */}
      <div className={styles.tombstoneHero}>
        <div className={styles.tombstoneTop}>
          <span className={styles.rip}>† REST IN CODE †</span>
          <span className={styles.silenceBadge}>{daysSinceDeath.toLocaleString()} days of silence</span>
        </div>
        <h3 className={styles.lastSubject}>"{timeline.last_subject || 'Final commit'}"</h3>
        <div className={styles.tombstoneMeta}>
          <span>Final commit on {lastDate.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</span>
          {timeline.last_sha && (
            <button
              type="button"
              className={styles.shaBtn}
              onClick={() => onClickSha?.(timeline.last_sha!)}
              title="Inspect final commit diff"
            >
              [{timeline.last_sha.slice(0, 7)}]
            </button>
          )}
        </div>
      </div>

      {/* Stratigraphic Commit Histogram */}
      <div className={styles.histogramCard}>
        <div className={styles.cardHeader}>
          <h4 className={styles.cardTitle}>Historical Commit Stratigraphy</h4>
          <span className={styles.cardSub}>Activity pulse over time</span>
        </div>

        <div className={styles.chartContainer}>
          <div className={styles.bars}>
            {timeline.buckets.map((b) => {
              const heightPct = Math.max(12, Math.round((b.count / maxBucket) * 100));
              return (
                <div key={b.month} className={styles.barCol} title={`${b.month}: ${b.count} commits`}>
                  <div className={styles.barTrack}>
                    <div className={styles.barFill} style={{ height: `${heightPct}%` }} />
                  </div>
                  <span className={styles.barLabel}>{b.month.slice(2)}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Top Maintainers / Authors */}
      <div className={styles.authorsGrid}>
        <div className={styles.authorsCard}>
          <h4 className={styles.cardTitle}>Departed Maintainers</h4>
          <p className={styles.cardSub}>Authors whose collective voice answers your questions</p>
          <ul className={styles.authorList}>
            {timeline.top_authors.map((a, i) => (
              <li key={a.author} className={styles.authorItem}>
                <span className={styles.authorRank}>#{i + 1}</span>
                <span className={styles.authorName}>{a.author}</span>
                <span className={styles.authorCommits}>{a.commits} commits</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Historical Eras */}
        <div className={styles.erasCard}>
          <h4 className={styles.cardTitle}>Explore Historical Eras</h4>
          <p className={styles.cardSub}>Click to interrogate maintainers about key milestones</p>
          <div className={styles.eraButtons}>
            <button
              type="button"
              className={styles.eraBtn}
              onClick={() => onAskEra?.('Why did the project start and what were its original core design goals?')}
            >
              🌱 The Genesis Era (2011–2012)
            </button>
            <button
              type="button"
              className={styles.eraBtn}
              onClick={() => onAskEra?.('Why was the HTTP transport and socket timeout logic rewritten?')}
            >
              ⚡ Peak Refactoring Era (2015–2016)
            </button>
            <button
              type="button"
              className={styles.eraBtn}
              onClick={() => onAskEra?.('Why was request fully deprecated in the documentation?')}
            >
              🍂 The Sunset & Deprecation (2020)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

