/**
 * Unit tests for the replay Source (web/src/replay.ts).
 * The fixture below is a hand-written plumbing fixture for the test only; it is
 * never shipped. Real demo data comes from scripts/record_replays.py.
 */
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { replaySource, setReplaySpeed } from '../web/src/replay.ts';

const SHA = 'a'.repeat(40);

const index = {
  version: 1,
  repos: [
    {
      id: 'demo',
      name: 'demo',
      commit_count: 3,
      head_sha: SHA,
      recorded_at: '2026-01-01T00:00:00Z',
      recordings: [
        { id: 'q1', question: 'Why was X removed?', trap: false, file: 'demo/q1.json' },
      ],
    },
  ],
};

const recording = {
  version: 1,
  repo_id: 'demo',
  question: 'Why was X removed?',
  backend: 'test',
  model: null,
  recorded_at: '2026-01-01T00:00:00Z',
  commits: { [SHA]: { sha: SHA, short: SHA.slice(0, 7), subject: 'remove X' } },
  runs: {
    guarded: {
      events: [
        { t: 0, event: 'evidence', data: '{"evidence":[]}' },
        { t: 5000, event: 'token', data: '{"token":"guarded "}' },
        { t: 5010, event: 'done', data: '{"mode":"guarded"}' },
      ],
    },
    raw: {
      events: [
        { t: 0, event: 'token', data: '{"token":"raw "}' },
        { t: 1, event: 'done', data: '{"mode":"raw"}' },
      ],
    },
  },
};

beforeEach(() => {
  setReplaySpeed(1_000_000); // no real sleeping in tests
  globalThis.fetch = async (url) => {
    const u = String(url);
    const body = u.endsWith('replays/index.json')
      ? index
      : u.endsWith('replays/demo/q1.json')
        ? recording
        : null;
    return body
      ? { ok: true, status: 200, json: async () => body }
      : { ok: false, status: 404, json: async () => ({}) };
  };
});

async function collect(gen) {
  const out = [];
  for await (const e of gen) out.push(e);
  return out;
}

test('repos() maps the index to RepoSummary with replay: paths', async () => {
  const repos = await replaySource.repos();
  assert.equal(repos.length, 1);
  assert.equal(repos[0].path, 'replay:demo');
  assert.equal(repos[0].commit_count, 3);
});

test('ask() replays recorded events verbatim and in order', async () => {
  const events = await collect(
    replaySource.ask({ question: '  why was x removed?  ', repo: 'replay:demo', mode: 'guarded' })
  );
  assert.deepEqual(
    events.map((e) => e.event),
    ['evidence', 'token', 'done']
  );
  assert.equal(events[1].data, '{"token":"guarded "}');
});

test('ask() in raw mode replays the raw run', async () => {
  const events = await collect(
    replaySource.ask({ question: 'Why was X removed?', repo: 'replay:demo', mode: 'raw' })
  );
  assert.equal(events[0].data, '{"token":"raw "}');
});

test('ask() with an unrecorded question yields a friendly error then done', async () => {
  const events = await collect(
    replaySource.ask({ question: 'Something else?', repo: 'replay:demo' })
  );
  assert.deepEqual(
    events.map((e) => e.event),
    ['error', 'done']
  );
  assert.match(JSON.parse(events[0].data).message, /recorded/);
});

test('ask() stops promptly when aborted', async () => {
  const ac = new AbortController();
  ac.abort();
  const events = await collect(
    replaySource.ask({
      question: 'Why was X removed?',
      repo: 'replay:demo',
      signal: ac.signal,
    })
  );
  assert.equal(events.length, 0);
});

test('summon() resolves a known repo and rejects an unknown one', async () => {
  const ok = await collect(replaySource.summon({ repo: 'replay:demo' }));
  assert.equal(ok.at(-1).event, 'done');
  assert.equal(JSON.parse(ok.at(-1).data).path, 'replay:demo');

  const bad = await collect(replaySource.summon({ repo: '/some/local/path' }));
  assert.equal(bad[0].event, 'error');
});

test('commit() resolves by short prefix and throws for unknown commits', async () => {
  const c = await replaySource.commit(SHA.slice(0, 7), 'replay:demo');
  assert.equal(c.subject, 'remove X');
  await assert.rejects(() => replaySource.commit('deadbee', 'replay:demo'), /not part of/);
});

test('questions() returns the curated list', async () => {
  assert.deepEqual(await replaySource.questions('replay:demo'), ['Why was X removed?']);
});

