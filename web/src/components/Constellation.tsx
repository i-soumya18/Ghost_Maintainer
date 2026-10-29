import React from 'react';
import type { Evidence } from '../types';
import styles from './Constellation.module.css';

interface ConstellationProps {
  evidence: Evidence[];
  highlightedSha?: string | null;
  onHoverSha?: (sha: string | null) => void;
  onClickSha?: (sha: string) => void;
}

export const Constellation: React.FC<ConstellationProps> = ({
  evidence,
  highlightedSha,
  onHoverSha,
  onClickSha,
}) => {
  if (!evidence || evidence.length === 0) {
    return null;
  }

  // Calculate coordinates in a circular or constellation layout
  const width = 360;
  const height = 180;
  const centerX = width / 2;
  const centerY = height / 2;
  const radiusX = width * 0.38;
  const radiusY = height * 0.35;

  const nodes = evidence.slice(0, 8).map((item, idx, arr) => {
    const angle = (idx / arr.length) * 2 * Math.PI - Math.PI / 2;
    const x = centerX + radiusX * Math.cos(angle);
    const y = centerY + radiusY * Math.sin(angle);
    const sha = item.commit.short_sha || item.commit.sha.slice(0, 7);
    const isHighlighted =
      Boolean(highlightedSha) &&
      (highlightedSha === sha || sha.startsWith(highlightedSha!));
    return {
      id: item.id,
      sha,
      fullSha: item.commit.sha,
      score: item.relevance_score || 0,
      subject: item.commit.message,
      x,
      y,
      isHighlighted,
    };
  });

  return (
    <div className={styles.constellationCard} role="region" aria-label="Citation Constellation">
      <div className={styles.header}>
        <span className={styles.constellationTag}>CITATION CONSTELLATION</span>
        <span className={styles.nodeCount}>{nodes.length} connected anchors</span>
      </div>

      <svg
        className={styles.svg}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden="true"
      >
        <defs>
          <filter id="spiritGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Constellation Connecting Web Lines */}
        {nodes.map((node, i) =>
          nodes.slice(i + 1).map((target, j) => (
            <line
              key={`${node.sha}-${target.sha}-${j}`}
              x1={node.x}
              y1={node.y}
              x2={target.x}
              y2={target.y}
              className={
                node.isHighlighted || target.isHighlighted
                  ? styles.activeLine
                  : styles.edgeLine
              }
            />
          ))
        )}

        {/* Center Pivot Point */}
        <circle cx={centerX} cy={centerY} r="3" className={styles.centerPivot} />

        {/* Commit Nodes */}
        {nodes.map((node) => (
          <g
            key={node.sha}
            className={`${styles.nodeGroup} ${node.isHighlighted ? styles.highlightedNode : ''}`}
            transform={`translate(${node.x}, ${node.y})`}
            onMouseEnter={() => onHoverSha?.(node.sha)}
            onMouseLeave={() => onHoverSha?.(null)}
            onClick={() => onClickSha?.(node.fullSha)}
          >
            <circle
              r={node.isHighlighted ? '10' : '7'}
              className={styles.nodeCircle}
              filter={node.isHighlighted ? 'url(#spiritGlow)' : undefined}
            />
            <text
              y="16"
              className={styles.nodeLabel}
              textAnchor="middle"
            >
              {node.sha}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
};

