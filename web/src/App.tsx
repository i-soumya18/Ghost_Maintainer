import React, { useState, useEffect, useCallback, useRef } from 'react';
import type {
  RepoInfo,
  RepoSummary,
  Message,
  SummonState,
  AskState,
  Evidence,
} from './types';
import { source } from './source';
import { TopBar, type ActiveTab } from './components/TopBar';
import { SummonScreen } from './components/SummonScreen';
import { IndexingProgress } from './components/IndexingProgress';
import { SeanceScreen } from './components/SeanceScreen';
import { EvidenceRail } from './components/EvidenceRail';
import { CommitDrawer } from './components/CommitDrawer';
import { LieDetector } from './components/LieDetector';
import { Graveyard } from './components/Graveyard';
import { ProofCardModal } from './components/ProofCard';
import type { ProofCardData } from './lib/share';
import { playGhostChoir } from './lib/sound';
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
      for await (const { event, data } of source.summon({
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
        for await (const { event, data } of source.ask({
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
  const [backend, setBackend] = useState<string | null>(null);
  const [curatedQuestions, setCuratedQuestions] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<ActiveTab>('seance');
  const [proofModalData, setProofModalData] = useState<ProofCardData | null>(null);
  const [konamiNotice, setKonamiNotice] = useState<string | null>(null);
  const [mobileEvidenceOpen, setMobileEvidenceOpen] = useState(false);

  const pendingAutoQuestion = useRef<string | null>(null);
  const konamiSeq = useRef<string[]>([]);

  const { state: summonState, summon, reset: resetSummon } = useSummon();
  const { state: askState, ask, abort: abortAsk, reset: resetAsk } = useAsk();

  useEffect(() => {
    source.repos().then(setKnownRepos).catch(() => {});
    source.health()
      .then((h) => setBackend(h.backend ?? null))
      .catch(() => {});
  }, []);

  // Konami Code Easter Egg (↑ ↑ ↓ ↓ ← → ← → B A)
  useEffect(() => {
    const TARGET = [
      'ArrowUp',
      'ArrowUp',
      'ArrowDown',
      'ArrowDown',
      'ArrowLeft',
      'ArrowRight',
      'ArrowLeft',
      'ArrowRight',
      'b',
      'a',
    ];
    const handleKeyDown = (e: KeyboardEvent) => {
      konamiSeq.current = [...konamiSeq.current, e.key].slice(-10);
      if (konamiSeq.current.join(',').toLowerCase() === TARGET.join(',').toLowerCase()) {
        playGhostChoir();
        setKonamiNotice('👻 Séance Choir Awakened! The spirits sing for Hacktoberfest 2026.');
        setTimeout(() => setKonamiNotice(null), 5000);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

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

  useEffect(() => {
    if (summonState.phase === 'done' && summonState.activeRepo) {
      setActiveRepo(summonState.activeRepo);
      source
        .questions(summonState.activeRepo.path)
        .then(setCuratedQuestions)
        .catch(() => setCuratedQuestions([]));
      resetSummon();
      setMessages([]);
      setActiveTab('seance');

      // Check if an auto-question was pending from Gallery click
      if (pendingAutoQuestion.current) {
        const q = pendingAutoQuestion.current;
        pendingAutoQuestion.current = null;
        setTimeout(() => handleAsk(q), 150);
      }
    }
  }, [summonState, resetSummon, handleAsk]);

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

  const handleSummonWithQuestion = useCallback(
    (repoPath: string, autoQuestion?: string) => {
      if (autoQuestion) {
        pendingAutoQuestion.current = autoQuestion;
      }
      summon(repoPath);
    },
    [summon]
  );

  const handleChangeRepo = useCallback(() => {
    abortAsk();
    resetAsk();
    setActiveRepo(null);
    setMessages([]);
    setDrawerSha(null);
    setActiveTab('seance');
    setMobileEvidenceOpen(false);
    source.repos().then(setKnownRepos).catch(() => {});
  }, [abortAsk, resetAsk]);

  const handleShareProof = useCallback(
    (assistantMsg: Message) => {
      if (!activeRepo) return;
      const msgIdx = messages.findIndex((m) => m.id === assistantMsg.id);
      const userQ = msgIdx > 0 && messages[msgIdx - 1].role === 'user'
        ? messages[msgIdx - 1].text
        : 'Interrogating codebase history';

      const citations = assistantMsg.verdict?.sentences?.flatMap((s) => s.citations) || [];
      const uniqueHashes = Array.from(new Set(citations));

      setProofModalData({
        repoName: activeRepo.name,
        question: userQ,
        answerSnippet: assistantMsg.text,
        verifiedCount: assistantMsg.verdict?.verified_count || uniqueHashes.length,
        totalCitations: assistantMsg.verdict?.total_count || uniqueHashes.length,
        citedHashes: uniqueHashes,
      });
    },
    [activeRepo, messages]
  );

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
        backend={backend}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      {konamiNotice && (
        <div className={styles.konamiBanner} role="status">
          {konamiNotice}
        </div>
      )}

      <div className={styles.mainLayout}>
        {summonState.phase === 'indexing' ? (
          <IndexingProgress
            processed={summonState.processed}
            total={summonState.total}
            phaseName={summonState.phaseName}
            repoName={activeRepo?.name}
          />
        ) : activeRepo ? (
          activeTab === 'compare' ? (
            <LieDetector
              repoName={activeRepo.name}
              onClickSha={setDrawerSha}
            />
          ) : activeTab === 'graveyard' ? (
            <Graveyard
              repoPath={activeRepo.path}
              repoName={activeRepo.name}
              onAskEra={(q) => {
                setActiveTab('seance');
                handleAsk(q);
              }}
              onClickSha={setDrawerSha}
            />
          ) : (
            <>
              <SeanceScreen
                messages={messages}
                onAsk={handleAsk}
                streamPhase={askState.phase}
                highlightedSha={highlightedSha}
                onHoverSha={setHighlightedSha}
                onClickSha={setDrawerSha}
                repoName={activeRepo.name}
                suggestions={curatedQuestions}
                onShareProof={handleShareProof}
                onOpenLieDetector={() => setActiveTab('compare')}
                evidenceCount={latestEvidence.length}
                onToggleMobileEvidence={() => setMobileEvidenceOpen((v) => !v)}
              />
              <EvidenceRail
                evidence={latestEvidence}
                highlightedSha={highlightedSha}
                onHoverSha={setHighlightedSha}
                onClickSha={setDrawerSha}
                isLoading={askState.phase === 'retrieving'}
                isOpenOnMobile={mobileEvidenceOpen}
                onCloseMobile={() => setMobileEvidenceOpen(false)}
              />
            </>
          )
        ) : (
          <SummonScreen
            onSummon={handleSummonWithQuestion}
            knownRepos={knownRepos}
            replayMode={source.mode === 'replay'}
            isLoading={false}
            error={summonState.error}
            onOpenLieDetector={() => {
              // Quick open demo repo in Lie Detector
              summon('request');
              setActiveTab('compare');
            }}
          />
        )}
      </div>

      <CommitDrawer
        sha={drawerSha}
        repoPath={activeRepo?.path || ''}
        onClose={() => setDrawerSha(null)}
      />

      {proofModalData && (
        <ProofCardModal
          data={proofModalData}
          onClose={() => setProofModalData(null)}
        />
      )}
    </div>
  );
};
