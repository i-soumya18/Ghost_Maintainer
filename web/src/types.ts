export interface RepoInfo {
  name: string;
  path: string;
  commitCount: number;
}

export interface RepoSummary {
  id: string;
  name: string;
  path: string;
  head_sha: string | null;
  commit_count: number;
  last_indexed: string;
}

export interface FileChange {
  path: string;
  added: number;
  deleted: number;
  is_binary?: boolean;
}

export interface Commit {
  sha: string;
  short_sha: string;
  message: string;
  author: string;
  date: string;
  files_changed: string[];
}

export interface CommitDetails {
  sha: string;
  short: string;
  author: string;
  email: string;
  date: string;
  subject: string;
  body: string;
  files: FileChange[];
  hunks: string[];
  diff: string | null;
}

export interface Evidence {
  id: string;
  commit: Commit;
  snippet: string;
  relevance_score?: number;
}

export type CitationStatus = 'pending' | 'verified' | 'unverified' | 'uncited';

export interface SentenceVerdict {
  sentence_index: number;
  text: string;
  status: 'verified' | 'unverified' | 'uncited';
  citations: string[];
}

export interface Verdict {
  sentences: SentenceVerdict[];
  verified_count: number;
  total_count: number;
}

export type StreamPhase =
  | 'idle'
  | 'retrieving'
  | 'streaming'
  | 'reconsidering'
  | 'verdict'
  | 'silence'
  | 'done'
  | 'error';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  evidence: Evidence[];
  streamPhase: StreamPhase;
  verdict?: Verdict;
  reconsidering?: {
    reason: string;
    attempt?: number;
  };
  error?: string;
  timestamp: Date;
}

export interface SummonState {
  phase: 'idle' | 'indexing' | 'done' | 'error';
  processed: number;
  total: number;
  phaseName: string;
  error: string | null;
  activeRepo: RepoInfo | null;
}

export interface AskState {
  phase: StreamPhase;
  rawText: string;
  evidence: Evidence[];
  verdict: Verdict | null;
  reconsidering: { reason: string; attempt: number } | null;
  error: string | null;
}
