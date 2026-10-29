import React, { useState, useRef, useEffect } from 'react';
import type { Message, StreamPhase } from '../types';
import { VoiceMessage } from './VoiceMessage';
import styles from './SeanceScreen.module.css';

interface SeanceScreenProps {
  messages: Message[];
  onAsk: (question: string) => void;
  streamPhase: StreamPhase;
  highlightedSha?: string | null;
  onHoverSha?: (sha: string | null) => void;
  onClickSha?: (sha: string) => void;
  repoName?: string;
}

const SUGGESTED_QUESTIONS = [
  'Why was the project deprecated?',
  'Why was the authentication subsystem rewritten?',
  'What were the breaking changes in the major release?',
];

export const SeanceScreen: React.FC<SeanceScreenProps> = ({
  messages,
  onAsk,
  streamPhase,
  highlightedSha,
  onHoverSha,
  onClickSha,
  repoName,
}) => {
  const [inputVal, setInputVal] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const isBusy =
    streamPhase === 'retrieving' ||
    streamPhase === 'streaming' ||
    streamPhase === 'reconsidering';

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamPhase]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputVal.trim() && !isBusy) {
      onAsk(inputVal.trim());
      setInputVal('');
    }
  };

  return (
    <main
      className={styles.container}
      role="region"
      aria-label="Conversation with the departed maintainers"
    >
      <div className={styles.scrollArea}>
        {messages.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.candleIcon}>🕯</div>
            <h2 className={styles.emptyTitle}>The Séance is Open</h2>
            <p className={styles.emptyText}>
              Ask about the choices, migrations, deprecations, and secrets buried within the
              commit history of <strong>{repoName || 'this repository'}</strong>.
            </p>

            <div className={styles.suggestions}>
              <span className={styles.suggestionsHeader}>Suggested inquiries:</span>
              <div className={styles.suggestionList}>
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className={styles.suggestionBtn}
                    onClick={() => onAsk(q)}
                    disabled={isBusy}
                  >
                    "{q}"
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className={styles.messageList}>
            {messages.map((msg) => (
              <VoiceMessage
                key={msg.id}
                message={msg}
                highlightedSha={highlightedSha}
                onHoverSha={onHoverSha}
                onClickSha={onClickSha}
              />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className={styles.inputArea}>
        <form onSubmit={handleSubmit} className={styles.form}>
          <input
            type="text"
            className={styles.input}
            placeholder={
              isBusy
                ? 'The spirits are speaking…'
                : 'Ask the departed maintainers…'
            }
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            disabled={isBusy}
            aria-label="Ask a question"
          />
          <button
            type="submit"
            className={styles.sendBtn}
            disabled={!inputVal.trim() || isBusy}
            aria-label="Send inquiry"
          >
            {isBusy ? '…' : 'Inquire'}
          </button>
        </form>
      </div>
    </main>
  );
};
