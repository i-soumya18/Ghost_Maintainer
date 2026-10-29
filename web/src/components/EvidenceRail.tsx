import React from 'react';
import type { Evidence } from '../types';
import { CommitCard } from './CommitCard';
import { Constellation } from './Constellation';
import { Wick } from './Wick';
import styles from './EvidenceRail.module.css';

interface EvidenceRailProps {
  evidence: Evidence[];
  highlightedSha?: string | null;
  onHoverSha?: (sha: string | null) => void;
  onClickSha?: (sha: string) => void;
  isLoading?: boolean;
}

export const EvidenceRail: React.FC<EvidenceRailProps> = ({
  evidence,
  highlightedSha,
  onHoverSha,
  onClickSha,
  isLoading = false,
}) => {
  return (
    <aside className={styles.rail} aria-label="Archaeological evidence cards">
      <div className={styles.stickyHeader}>
        <h3 className={styles.title}>
          <span className={styles.flame}><Wick mood="idle" size={18} /></span> Archive Evidence
        </h3>
        <span className={styles.count}>
          {evidence.length > 0
            ? `${evidence.length} commits cited`
            : 'Awaiting query'}
        </span>
      </div>

      <div className={styles.scrollArea}>
        {evidence.length > 1 && (
          <Constellation
            evidence={evidence}
            highlightedSha={highlightedSha}
            onHoverSha={onHoverSha}
            onClickSha={onClickSha}
          />
        )}

        {isLoading && evidence.length === 0 && (
          <div className={styles.emptyState}>
            <div className={styles.pulsingFlame}><Wick mood="listening" size={40} /></div>
            <p className={styles.emptyText}>Consulting the commit ledger…</p>
          </div>
        )}

        {!isLoading && evidence.length === 0 && (
          <div className={styles.emptyState}>
            <p className={styles.emptyText}>
              When you ask a question, the relevant historical commits appear here before
              the ghost speaks.
            </p>
          </div>
        )}

        {evidence.map((item) => {
          const itemSha = item.commit.short_sha || item.commit.sha.slice(0, 7);
          const isHighlighted =
            Boolean(highlightedSha) &&
            (highlightedSha === itemSha || item.commit.sha.startsWith(highlightedSha!));

          return (
            <CommitCard
              key={item.id || item.commit.sha}
              evidence={item}
              isHighlighted={isHighlighted}
              onHover={onHoverSha}
              onClick={onClickSha}
            />
          );
        })}
      </div>
    </aside>
  );
};
