import React from 'react';
import styles from './Wick.module.css';

export type WickMood =
  | 'idle'
  | 'listening'
  | 'speaking'
  | 'reconsidering'
  | 'silent';

interface WickProps {
  mood?: WickMood;
  size?: number;
  /** Decorative by default; pass a label to expose it to assistive tech. */
  label?: string;
  className?: string;
}

/**
 * Wick: a candle-flame ghost. Original artwork, pure SVG, no external assets.
 * Animation is CSS-only and disabled under prefers-reduced-motion.
 */
export const Wick: React.FC<WickProps> = ({
  mood = 'idle',
  size = 48,
  label,
  className,
}) => {
  const closedEyes = mood === 'silent';
  return (
    <svg
      className={`${styles.wick} ${styles[mood]} ${className ?? ''}`}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <defs>
        <radialGradient id="wick-glow" cx="50%" cy="45%" r="55%">
          <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.55" />
          <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle className={styles.glow} cx="32" cy="32" r="30" fill="url(#wick-glow)" />
      {/* flame wisp */}
      <path
        className={styles.flame}
        d="M32 3c3 5 5 8 2 12-1.4 1.8-3.6 1.8-4.4 0C28.6 12 30 8 32 3z"
        fill="var(--color-accent)"
      />
      {/* ghost body */}
      <path
        className={styles.body}
        d="M32 14c-10 0-17 7.6-17 17v21c0 1.6 1.9 2.4 3 1.2l3.2-3.4 3.6 3.6c.8.8 2 .8 2.8 0L32 50l4.4 3.4c.8.8 2 .8 2.8 0l3.6-3.6 3.2 3.4c1.1 1.2 3 .4 3-1.2V31c0-9.400-7-17-17-17z"
        fill="var(--color-text)"
        fillOpacity="0.94"
      />
      {/* eyes */}
      {closedEyes ? (
        <g stroke="var(--color-bg)" strokeWidth="2.2" strokeLinecap="round" fill="none">
          <path d="M22 31q3 2.4 6 0" />
          <path d="M36 31q3 2.4 6 0" />
        </g>
      ) : (
        <g className={styles.eyes} fill="var(--color-bg)">
          <ellipse cx="25" cy="31" rx="3" ry={mood === 'listening' ? 4 : 3.4} />
          <ellipse cx="39" cy="31" rx="3" ry={mood === 'listening' ? 4 : 3.4} />
        </g>
      )}
      {/* mouth */}
      {mood === 'speaking' ? (
        <ellipse className={styles.mouth} cx="32" cy="40" rx="3" ry="2.4" fill="var(--color-bg)" />
      ) : mood === 'reconsidering' ? (
        <path d="M27 40h10" stroke="var(--color-bg)" strokeWidth="2" strokeLinecap="round" />
      ) : mood === 'silent' ? (
        <path d="M28 41q4-2 8 0" stroke="var(--color-bg)" strokeWidth="2" strokeLinecap="round" fill="none" />
      ) : (
        <path d="M28 39.500q4 3 8 0" stroke="var(--color-bg)" strokeWidth="2" strokeLinecap="round" fill="none" />
      )}
    </svg>
  );
};

