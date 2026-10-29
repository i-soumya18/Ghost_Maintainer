import type { RepoSummary, CommitDetails } from './types';

const API_BASE = '/api';

export async function fetchRepos(): Promise<RepoSummary[]> {
  const res = await fetch(`${API_BASE}/repos`);
  if (!res.ok) {
    throw new Error(`Failed to fetch repos: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchCommitDetails(
  sha: string,
  repoPath: string
): Promise<CommitDetails> {
  const url = new URL(`${API_BASE}/commit/${encodeURIComponent(sha)}`, window.location.href);
  url.searchParams.set('repo', repoPath);
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`Failed to fetch commit: ${res.statusText}`);
  }
  return res.json();
}

export interface AskParams {
  question: string;
  repo: string;
  mode?: 'guarded' | 'raw';
  backend?: string;
  signal?: AbortSignal;
}

export async function* askQuestionStream(
  params: AskParams
): AsyncGenerator<{ event: string; data: string }> {
  const url = new URL(`${API_BASE}/ask`, window.location.href);
  url.searchParams.set('q', params.question);
  url.searchParams.set('repo', params.repo);
  url.searchParams.set('mode', params.mode ?? 'guarded');
  if (params.backend) {
    url.searchParams.set('backend', params.backend);
  }

  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: { Accept: 'text/event-stream' },
    signal: params.signal,
  });

  if (!res.ok) {
    throw new Error(`Ask failed: ${res.statusText}`);
  }
  if (!res.body) {
    throw new Error('No response body');
  }

  yield* parseSSEStream(res.body, params.signal);
}

export interface SummonParams {
  repo: string;
  mode?: string;
  signal?: AbortSignal;
}

export async function* summonRepoStream(
  params: SummonParams
): AsyncGenerator<{ event: string; data: string }> {
  const res = await fetch(`${API_BASE}/summon`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream, application/json',
    },
    body: JSON.stringify({
      path: params.repo,
      repo: params.repo,
      source: params.repo,
      mode: params.mode,
    }),
    signal: params.signal,
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => res.statusText);
    throw new Error(`Summon failed: ${errText}`);
  }

  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const data = await res.json();
    yield { event: 'done', data: JSON.stringify(data) };
    return;
  }

  if (!res.body) {
    throw new Error('No response body');
  }

  yield* parseSSEStream(res.body, params.signal);
}

async function* parseSSEStream(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal
): AsyncGenerator<{ event: string; data: string }> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventType = 'message';
  let eventData = '';

  try {
    while (!(signal && signal.aborted)) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const rawLine of lines) {
        const line = rawLine.replace(/\r$/, '');
        if (line.startsWith('event:')) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          const chunk = line.slice(5).trim();
          eventData = eventData ? `${eventData}\n${chunk}` : chunk;
        } else if (line === '') {
          if (eventData) {
            yield { event: eventType, data: eventData };
          }
          eventType = 'message';
          eventData = '';
        }
      }
    }

    if (eventData) {
      yield { event: eventType, data: eventData };
    }
  } finally {
    reader.releaseLock();
  }
}
