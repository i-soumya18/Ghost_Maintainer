import React, { useState, useEffect, useCallback, useRef } from 'react';
import type {
  RepoInfo,
  RepoSummary,
  Message,
  SummonState,
  AskState,
  Evidence,
} from './types';
import { fetchRepos, summonRepoStream, askQuestionStream } from './api';
import { TopBar } from './components/TopBar';
import { SummonScreen } from './components/SummonScreen';
import { IndexingProgress } from './components/IndexingProgress';
import { SeanceScreen } from './components/SeanceScreen';
import { EvidenceRail } from './components/EvidenceRail';
import { CommitDrawer } from './components/CommitDrawer';
import styles from './styles/App.module.css';

const initialSummonState: SummonState = {
  phase: 'idle',
  processed: 0,
  total: 0,
  phaseName: '',
  error: null,
  activeRepo: null,
};

function useSummon() {
  const [state, setState] = useState<SummonState>(initialSummonState);
  const abortRef = useRef<AbortController | null>(null);

  const summon = useCallback(async (repoPath: string) => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setState({
      ...initialSummonState,
      phase: 'indexing',
      phaseName: 'Gathering memories…',
    });

    try {
      for await (const { event, data } of summonRepoStream({
        repo: repoPath,
        signal: ac.signal,
      })) {
        if (ac.signal.aborted) break;

        switch (event) {
          case 'progress': {
            try {
              const p = JSON.parse(data);
              setState((prev) => ({
                ...prev,
                phase: 'indexing',
                processed: p.processed ?? prev.processed,
                total: p.total ?? prev.total,
                phaseName: p.message || p.phase || prev.phaseName,
              }));
            } catch {
              // Ignore json parse error
            }
            break;
          }
          case 'done': {
            try {
              const d = JSON.parse(data);
              const active: RepoInfo = {
                name:
                  d.name ||
                  repoPath.split(/[/\\\\]/).filter(Boolean).pop() ||
                  repoPath,
                path: d.path || repoPath,
                commitCount: d.commit_count || 0,
              };
              setState((prev) => ({
                ...prev,
                phase: 'done',
                activeRepo: active,
              }));
            } catch {
              setState((prev) => ({ ...prev, phase: 'done' }));
            }
            break;
          }
          case 'error': {
            try {
              const err = JSON.parse(data);
              setState((prev) => ({
                ...prev,
                phase: 'error',
                error: err.message || 'Indexing failed',
              }));
            } catch {
              setState((prev) => ({ ...prev, phase: 'error', error: data }));
            }
            break;
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError') return;
      setState((prev) => ({
        ...prev,
        phase: 'error',
        error: (err as Error)?.message ?? 'Unknown error',
      }));
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(initialSummonState);
  }, []);

  return { state, summon, reset };
}

const initialAskState: AskState = {
  phase: 'idle',
  rawText: '',
  evidence: [],
  verdict: null,
  reconsidering: null,
  error: null,
};

function useAsk() {
  const [state, setState] = useState<AskState>(initialAskState);
  const abortRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const ask = useCallback(
    async (
      question: string,
      repo: string,
      mode: 'guarded' | 'raw' = 'guarded'
    ) => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      setState({
        ...initialAskState,
        phase: 'retrieving',
      });

      try {
        for await (const { event, data } of askQuestionStream({
          question,
          repo,
          mode,
          signal: ac.signal,
        })) {
          if (ac.signal.aborted) break;

          switch (event) {
            case 'evidence': {
              try {
                const parsed = JSON.parse(data);
                let evidenceItems: Evidence[] = [];
                if (Array.isArray(parsed.evidence)) {
                  evidenceItems = parsed.evidence.map((item: any) => ({
                    id:
                      item.commit?.short ||
                      item.commit?.sha?.slice(0, 7) ||
                      item.tag,
                    commit: {
                      sha: item.commit?.sha || '',
                      short_sha:
                        item.commit?.short ||
                        item.commit?.sha?.slice(0, 7) ||
                        '',
                      message:
                        item.commit?.subject || item.commit?.message || '',
                      author: item.commit?.author || '',
                      date: item.commit?.date || '',
                      files_changed: Array.isArray(item.commit?.files)
                        ? item.commit.files.map((f: any) =>
                            typeof f === 'string' ? f : f.path
                          )
                        : [],
                    },
                    snippet: item.commit?.body || '',
                    relevance_score: item.score,
                  }));
                } else if (parsed.id || parsed.commit) {
                  evidenceItems = [parsed];
                }
                setState((prev) => ({
                  ...prev,
                  phase:
                    prev.phase === 'retrieving' ? 'retrieving' : prev.phase,
                  evidence: evidenceItems,
                }));
              } catch {
                // Ignore parse error
              }
              break;
            }
            case 'token': {
              try {
                const parsed = JSON.parse(data);
                const chunk = parsed.text ?? parsed.token ?? '';
                setState((prev) => ({
                  ...prev,
                  phase: 'streaming',
                  rawText: prev.rawText + chunk,
                }));
              } catch {
                setState((prev) => ({
                  ...prev,
                  phase: 'streaming',
                  rawText: prev.rawText + data,
                }));
              }
              break;
            }
            case 'reconsidering': {
              try {
                const parsed = JSON.parse(data);
                setState((prev) => ({
                  ...prev,
                  phase: 'reconsidering',
                  rawText: '',
                  reconsidering: {
                    reason: parsed.reason || 'The spirits reconsider…',
                    attempt: parsed.attempt ?? 1,
                  },
                }));
              } catch {
                setState((prev) => ({
                  ...prev,
                  phase: 'reconsidering',
                  rawText: '',
                  reconsidering: {
                    reason: 'The spirits reconsider…',
                    attempt: 1,
                  },
                }));
              }
              break;
            }
            case 'verdict': {
              try {
                const parsed = JSON.parse(data);
                const sentences = (parsed.sentences || []).map(
                  (s: any, idx: number) => {
                    const citations = Array.isArray(s.citations)
                      ? s.citations.map((c: any) =>
                          typeof c === 'string'
                            ? c
                            : c.raw_hash || c.resolved_sha || ''
                        )
                      : [];
                    return {
                      sentence_index: idx,
                      text: s.text,
                      status: s.status || 'verified',
                      citations: citations.filter(Boolean),
                    };
                  }
                );
                const verifiedCount = sentences.filter(
                  (s: any) => s.status === 'verified'
                ).length;
                setState((prev) => ({
                  ...prev,
                  phase: 'verdict',
                  verdict: {
                    sentences,
                    verified_count: verifiedCount,
                    total_count: sentences.length,
                  },
                }));
              } catch {
                // Ignore parse error
              }
              break;
            }
            case 'done': {
              setState((prev) => {
                const isSilence =
                  !prev.rawText.trim() ||
                  prev.rawText.includes('The dead do not remember.');
                return {
                  ...prev,
                  phase: isSilence ? 'silence' : 'done',
                };
              });
              break;
            }
            case 'error': {
              try {
                const parsed = JSON.parse(data);
                setState((prev) => ({
                  ...prev,
                  phase: 'error',
                  error: parsed.message || 'An error occurred during séance.',
                }));
              } catch {
                setState((prev) => ({
                  ...prev,
                  phase: 'error',
                  error: data || 'An error occurred during séance.',
                }));
              }
              break;
            }
          }
        }
      } catch (err: unknown) {
        if ((err as Error)?.name === 'AbortError') return;
        setState((prev) => ({
          ...prev,
          phase: 'error',
          error: (err as Error)?.message ?? 'Unknown error',
        }));
      } finally {
        if (!ac.signal.aborted) {
          abortRef.current = null;
        }
      }
    },
    []
  );

  const reset = useCallback(() => {
    abort();
    setState(initialAskState);
  }, [abort]);

  return { state, ask, abort, reset };
}

export const App: React.FC = () => {
  const [activeRepo, setActiveRepo] = useState<RepoInfo | null>(null);
  const [knownRepos, setKnownRepos] = useState<RepoSummary[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [highlightedSha, setHighlightedSha] = useState<string | null>(null);
  const [drawerSha, setDrawerSha] = useState<string | null>(null);

  const { state: summonState, summon, reset: resetSummon } = useSummon();
  const { state: askState, ask, abort: abortAsk, reset: resetAsk } = useAsk();

  useEffect(() => {
    fetchRepos().then(setKnownRepos).catch(() => {});
  }, []);

  useEffect(() => {
    if (summonState.phase === 'done' && summonState.activeRepo) {
      setActiveRepo(summonState.activeRepo);
      resetSummon();
      setMessages([]);
    }
  }, [summonState, resetSummon]);

  useEffect(() => {
    if (askState.phase !== 'idle') {
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const last = prev[prev.length - 1];
        if (last.role !== 'assistant') return prev;

        const updated: Message = {
          ...last,
          text: askState.rawText,
          evidence:
            askState.evidence.length > 0 ? askState.evidence : last.evidence,
          verdict: askState.verdict ?? last.verdict,
          streamPhase: askState.phase,
          reconsidering: askState.reconsidering ?? undefined,
          error: askState.error ?? undefined,
        };
        return [...prev.slice(0, -1), updated];
      });
    }
  }, [askState]);

  const handleAsk = useCallback(
    (question: string) => {
      if (!activeRepo) return;

      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        text: question,
        evidence: [],
        streamPhase: 'idle',
        timestamp: new Date(),
      };

      const assistantMsg: Message = {
        id: `assistant-${Date.now() + 1}`,
        role: 'assistant',
        text: '',
        evidence: [],
        streamPhase: 'retrieving',
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      ask(question, activeRepo.path, 'guarded');
    },
    [activeRepo, ask]
  );

  const handleChangeRepo = useCallback(() => {
    abortAsk();
    resetAsk();
    setActiveRepo(null);
    setMessages([]);
    setDrawerSha(null);
    fetchRepos().then(setKnownRepos).catch(() => {});
  }, [abortAsk, resetAsk]);

  const latestEvidence =
    askState.evidence.length > 0
      ? askState.evidence
      : messages
          .slice()
          .reverse()
          .find((m) => m.evidence.length > 0)?.evidence || [];

  return (
    <div className={styles.appContainer}>
      <TopBar
        repo={activeRepo}
        onChangeRepo={activeRepo ? handleChangeRepo : undefined}
      />

      <div className={styles.mainLayout}>
        {summonState.phase === 'indexing' ? (
          <IndexingProgress
            processed={summonState.processed}
            total={summonState.total}
            phaseName={summonState.phaseName}
            repoName={activeRepo?.name}
          />
        ) : activeRepo ? (
          <>
            <SeanceScreen
              messages={messages}
              onAsk={handleAsk}
              streamPhase={askState.phase}
              highlightedSha={highlightedSha}
              onHoverSha={setHighlightedSha}
              onClickSha={setDrawerSha}
              repoName={activeRepo.name}
            />
            <EvidenceRail
              evidence={latestEvidence}
              highlightedSha={highlightedSha}
              onHoverSha={setHighlightedSha}
              onClickSha={setDrawerSha}
              isLoading={askState.phase === 'retrieving'}
            />
          </>
        ) : (
          <SummonScreen
            onSummon={summon}
            knownRepos={knownRepos}
            isLoading={false}
            error={summonState.error}
          />
        )}
      </div>

      <CommitDrawer
        sha={drawerSha}
        repoPath={activeRepo?.path || ''}
        onClose={() => setDrawerSha(null)}
      />
    </div>
  );
};
