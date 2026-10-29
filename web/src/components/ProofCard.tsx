import React, { useState } from 'react';
import { Wick } from './Wick';
import { downloadProofCard, getTwitterShareUrl, getRedditShareText, ProofCardData } from '../lib/share';
import { playGlassTick } from '../lib/sound';
import styles from './ProofCard.module.css';

interface ProofCardModalProps {
  data: ProofCardData | null;
  onClose: () => void;
}

export const ProofCardModal: React.FC<ProofCardModalProps> = ({ data, onClose }) => {
  const [copied, setCopied] = useState(false);

  if (!data) return null;

  const handleCopyLink = () => {
    playGlassTick();
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    });
  };

  const handleCopyReddit = () => {
    playGlassTick();
    const markdown = getRedditShareText(data);
    navigator.clipboard.writeText(markdown).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    });
  };

  const handleDownload = () => {
    playGlassTick();
    downloadProofCard(data);
  };

  return (
    <div className={styles.backdrop} onClick={onClose} role="dialog" aria-modal="true" aria-label="Archaeological Proof Card">
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <div className={styles.titleRow}>
            <Wick mood="idle" size={32} />
            <h3 className={styles.title}>Archaeological Proof Certificate</h3>
          </div>
          <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="Close proof certificate">
            ✕
          </button>
        </div>

        {/* Certificate Preview Card */}
        <div className={styles.certificate}>
          <div className={styles.certSeal}>
            <span className={styles.sealGlyph}>🕯</span>
            <span className={styles.sealText}>VERIFIED GIT OBJECT</span>
          </div>

          <div className={styles.certRepo}>{data.repoName}</div>
          <div className={styles.certInquiry}>
            <span className={styles.certLabel}>INQUIRY:</span>
            <p className={styles.certQuestion}>"{data.question}"</p>
          </div>

          <div className={styles.certResponseBox}>
            <span className={styles.certLabel}>DEPARTED VOICE:</span>
            <p className={styles.certResponse}>{data.answerSnippet}</p>
          </div>

          <div className={styles.certFooter}>
            <span className={styles.certStatus}>
              ✓ {data.verifiedCount} of {data.totalCitations || data.verifiedCount} claims verified in git object storage
            </span>
            <span className={styles.certWatermark}>Ghost Maintainer</span>
          </div>
        </div>

        {/* Action Controls */}
        <div className={styles.actions}>
          <button type="button" className={styles.downloadBtn} onClick={handleDownload}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download PNG Card (1200×630)
          </button>

          <a
            href={getTwitterShareUrl(data)}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.twitterBtn}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
            </svg>
            Share to X / Twitter
          </a>

          <button type="button" className={styles.copyBtn} onClick={handleCopyReddit}>
            {copied ? '✓ Markdown Copied!' : 'Copy Reddit / HN Markdown'}
          </button>

          <button type="button" className={styles.copyBtn} onClick={handleCopyLink}>
            {copied ? '✓ URL Copied!' : 'Copy Link'}
          </button>
        </div>
      </div>
    </div>
  );
};

