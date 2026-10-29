import type { CommitDetails, RepoSummary } from './types';
import {
  askQuestionStream,
  fetchCommitDetails,
  fetchHealth,
  fetchRepos,
  summonRepoStream,
  type AskParams,
  type Health,
  type SummonParams,
} from './api';
import { replaySource } from './replay';

export interface SSEEvent {
  event: string;
  data: string;
}

/**
 * Data source behind the UI. The same React tree runs against the live
 * FastAPI server ("live") or pre-recorded real sessions ("replay", used for
 * the static zero-install demo on GitHub Pages).
 */
export interface Source {
  mode: 'live' | 'replay';
  health(): Promise<Health>;
  repos(): Promise<RepoSummary[]>;
  summon(p: SummonParams): AsyncGenerator<SSEEvent>;
  ask(p: AskParams): AsyncGenerator<SSEEvent>;
  commit(sha: string, repoPath: string): Promise<CommitDetails>;
  /** Curated questions known to work for this repo (empty = use defaults). */
  questions(repoPath: string): Promise<string[]>;
}

export const liveSource: Source = {
  mode: 'live',
  health: fetchHealth,
  repos: fetchRepos,
  summon: summonRepoStream,
  ask: askQuestionStream,
  commit: fetchCommitDetails,
  questions: async () => [],
};

export function getSource(): Source {
  return import.meta.env.VITE_MODE === 'replay' ? replaySource : liveSource;
}

export const source: Source = getSource();

