import React, { useEffect, useState } from 'react';
import type { CommitDetails } from '../types';
import { source } from '../source';
import { Wick } from './Wick';
import styles from './CommitDrawer.module.css';

interface CommitDrawerProps {
  sha: string | null;
  repoPath: string;
  onClose: () => void;
}

export const CommitDrawer: React.FC<CommitDrawerProps> = ({
  sha,
  repoPath,
  onClose,
}) => {
  const [details, setDetails] = useState<CommitDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sha) {
      setDetails(null);
      setError(null);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);

    source.commit(sha, repoPath)
      .then((data) => {
        if (active) setDetails(data);
      })
      .catch((err) => {
        if (active) setError(err.message || 'Failed to load commit details');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [sha, repoPath]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!sha) return null;

  return (
    <div
      className={styles.overlay}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Commit details drawer"
    >
      <div
        className={styles.drawer}
        onClick={(e) => e.stopPropagation()}
        tabIndex={-1}
      >
        <header className={styles.drawerHeader}>
          <div className={styles.titleGroup}>
            <span className={styles.shaChip}>{sha.slice(0, 7)}</span>
            <h3 className={styles.title}>Commit Ledger</h3>
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close commit drawer"
          >
            ✕
          </button>
        </header>

        <div className={styles.content}>
          {loading && (
            <div className={styles.loadingState}>
              <span className={styles.candle}><Wick mood="silent" size={20} /></span>
              <p>Summoning commit details…</p>
            </div>
          )}

          {error && (
            <div className={styles.errorState}>
              <p>{error}</p>
            </div>
          )}

          {details && !loading && (
            <div className={styles.detailsBody}>
              <div className={styles.metaRow}>
                <div>
                  <strong>Author:</strong> {details.author} &lt;{details.email}&gt;
                </div>
                <div>
                  <strong>Date:</strong> {details.date}
                </div>
              </div>

              <h4 className={styles.subject}>{details.subject}</h4>
              {details.body && <p className={styles.body}>{details.body}</p>}

              {details.files && details.files.length > 0 && (
                <div className={styles.filesSection}>
                  <h5>Files Changed ({details.files.length})</h5>
                  <ul className={styles.fileList}>
                    {details.files.map((f) => (
                      <li key={f.path} className={styles.fileItem}>
                        <span className={styles.filePath}>{f.path}</span>
                        <span className={styles.stats}>
                          <span className={styles.added}>+{f.added}</span>
                          <span className={styles.deleted}>-{f.deleted}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {details.diff && (
                <div className={styles.diffSection}>
                  <h5>Diff</h5>
                  <pre className={styles.diffPre}>{details.diff}</pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
