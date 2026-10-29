import type { CommitDetails, RepoSummary } from './types';
import type { AskParams, Health, SummonParams } from './api';
import type { SSEEvent, Source } from './source';

/**
 * Replay data format (version 1)
 *
 * `replays/index.json` lists repos and their recordings. Each recording file
 * holds verbatim SSE events captured from a REAL run of the pipeline
 * (see scripts/record_replays.py) plus the slim commit payloads the drawer
 * needs. Nothing here is synthesised in the browser.
 */
export interface ReplayEvent {
  /** Milliseconds since the run started. */
  t: number;
  event: string;
  /** Raw JSON string exactly as it was on the SSE wire. */
  data: string;
}

export interface ReplayRun {
  events: ReplayEvent[];
}

export interface Recording {
  version: 1;
  repo_id: string;
  question: string;
  backend: string;
  model: string | null;
  recorded_at: string;
  commits: Record<string, CommitDetails>;
  runs: { guarded: ReplayRun; raw?: ReplayRun };
}

export interface ReplayIndexRecording {
  id: string;
  question: string;
  /** True when the question has a false premise and the ghost should refuse. */
  trap: boolean;
  file: string;
}

export interface ReplayIndexRepo {
  id: string;
  name: string;
  commit_count: number;
  head_sha: string | null;
  recorded_at: string;
  blurb?: string;
  recordings: ReplayIndexRecording[];
}

export interface ReplayIndex {
  version: 1;
  repos: ReplayIndexRepo[];
}

export const REPLAY_PREFIX = 'replay:';

let speed = 1;

/** 1 = recorded timing, 2 = twice as fast, Infinity = no delay. */
export function setReplaySpeed(multiplier: number): void {
  speed = multiplier > 0 ? multiplier : 1;
}

export function getReplaySpeed(): number {
  return speed;
}

const base = (): string => {
  const b = (import.meta as ImportMeta).env?.BASE_URL ?? '/';
  return b.endsWith('/') ? b : `${b}/`;
};

let indexPromise: Promise<ReplayIndex> | null = null;
const recordingCache = new Map<string, Promise<Recording>>();

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${base()}replays/${path}`);
  if (!res.ok) {
    throw new Error(`Could not load replay data (${path}): ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function loadIndex(): Promise<ReplayIndex> {
  indexPromise ??= getJson<ReplayIndex>('index.json');
  return indexPromise;
}

function loadRecording(file: string): Promise<Recording> {
  let p = recordingCache.get(file);
  if (!p) {
    p = getJson<Recording>(file);
    recordingCache.set(file, p);
  }
  return p;
}

function repoIdFromPath(repoPath: string): string {
  return repoPath.startsWith(REPLAY_PREFIX) ? repoPath.slice(REPLAY_PREFIX.length) : repoPath;
}

function normalise(q: string): string {
  return q.trim().replace(/\s+/g, ' ').toLowerCase();
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (ms <= 0 || signal?.aborted) {
      resolve();
      return;
    }
    const id = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(id);
        resolve();
      },
      { once: true }
    );
  });
}

function err(message: string): SSEEvent[] {
  return [
    { event: 'error', data: JSON.stringify({ message }) },
    { event: 'done', data: JSON.stringify({ mode: 'guarded', retries: 0 }) },
  ];
}

async function* playEvents(
  events: ReplayEvent[],
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  let last = 0;
  for (const ev of events) {
    if (signal?.aborted) return;
    const gap = Math.max(0, ev.t - last);
    last = ev.t;
    // Cap single gaps so slow model load times in a recording never feel like a hang.
    await sleep(Math.min(gap, 900) / speed, signal);
    yield { event: ev.event, data: ev.data };
  }
}

export const replaySource: Source = {
  mode: 'replay',

  async health(): Promise<Health> {
    return { status: 'ok', version: 'replay', backend: 'replay' };
  },

  async repos(): Promise<RepoSummary[]> {
    const index = await loadIndex();
    return index.repos.map((r) => ({
      id: r.id,
      name: r.name,
      path: `${REPLAY_PREFIX}${r.id}`,
      head_sha: r.head_sha,
      commit_count: r.commit_count,
      last_indexed: r.recorded_at,
    }));
  },

  async *summon(p: SummonParams): AsyncGenerator<SSEEvent> {
    const id = repoIdFromPath(p.repo);
    const index = await loadIndex();
    const repo = index.repos.find((r) => r.id === id || r.name === id);
    if (!repo) {
      for (const e of err(
        `"${p.repo}" is not in the replay gallery. Install Ghost Maintainer to summon your own repository.`
      )) {
        yield e;
      }
      return;
    }
    yield {
      event: 'progress',
      data: JSON.stringify({ phase: 'opening', message: 'Opening the archive\u2026', processed: 1, total: 2 }),
    };
    await sleep(350 / speed, p.signal);
    yield {
      event: 'done',
      data: JSON.stringify({
        id: repo.id,
        name: repo.name,
        path: `${REPLAY_PREFIX}${repo.id}`,
        head_sha: repo.head_sha,
        commit_count: repo.commit_count,
        indexed_at: repo.recorded_at,
        status: 'ready',
      }),
    };
  },

  async *ask(p: AskParams): AsyncGenerator<SSEEvent> {
    const id = repoIdFromPath(p.repo);
    const index = await loadIndex();
    const repo = index.repos.find((r) => r.id === id);
    const hit = repo?.recordings.find((r) => normalise(r.question) === normalise(p.question));
    if (!repo || !hit) {
      for (const e of err(
        'This hosted demo replays real recorded s\u00e9ances, so it can only answer the suggested questions. ' +
          'Install Ghost Maintainer to ask anything about any repository.'
      )) {
        yield e;
      }
      return;
    }
    const rec = await loadRecording(hit.file);
    const run = p.mode === 'raw' && rec.runs.raw ? rec.runs.raw : rec.runs.guarded;
    yield* playEvents(run.events, p.signal);
  },

  async commit(sha: string, repoPath: string): Promise<CommitDetails> {
    const id = repoIdFromPath(repoPath);
    const index = await loadIndex();
    const repo = index.repos.find((r) => r.id === id);
    const needle = sha.toLowerCase();
    for (const r of repo?.recordings ?? []) {
      const rec = await loadRecording(r.file);
      const key = Object.keys(rec.commits).find((k) => k === needle || k.startsWith(needle));
      if (key) return rec.commits[key];
    }
    throw new Error(`Commit ${sha} is not part of the recorded demo.`);
  },

  async questions(repoPath: string): Promise<string[]> {
    const id = repoIdFromPath(repoPath);
    const index = await loadIndex();
    return index.repos.find((r) => r.id === id)?.recordings.map((r) => r.question) ?? [];
  },
};

