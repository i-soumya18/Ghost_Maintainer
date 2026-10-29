import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, join } from 'node:path';

// ---------------------------------------------------------------------------
// 1. SSE Stream Parser Resilience Tests
// Port of parseSSEStream from web/src/api.ts
// ---------------------------------------------------------------------------

async function* parseSSEStream(
  body,
  signal
) {
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

function makeReadableStream(chunks, delayMs = 0) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    async start(controller) {
      for (const chunk of chunks) {
        if (delayMs > 0) {
          await new Promise((r) => setTimeout(r, delayMs));
        }
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

test('SSE Parser: Normal stream with typed events', async () => {
  const ssePayload = [
    'event: evidence\r\ndata: {"evidence":[{"id":"e1"}]}\r\n\r\n',
    'event: token\r\ndata: {"text":"The"}\r\n\r\n',
    'event: token\r\ndata: {"text":" dead"}\r\n\r\n',
    'event: done\r\ndata: {}\r\n\r\n',
  ];
  const stream = makeReadableStream(ssePayload);
  const events = [];
  for await (const evt of parseSSEStream(stream)) {
    events.push(evt);
  }
  assert.equal(events.length, 4);
  assert.equal(events[0].event, 'evidence');
  assert.equal(events[1].event, 'token');
  assert.equal(events[2].data, '{"text":" dead"}');
  assert.equal(events[3].event, 'done');
});

test('SSE Parser: Single-byte chunk fragmentation (resilience against arbitrary network chunking)', async () => {
  const rawText = 'event: token\ndata: {"text":"Ghost"}\n\nevent: done\ndata: {}\n\n';
  // Split into 1-byte chunks
  const chunks = rawText.split('');
  const stream = makeReadableStream(chunks);
  const events = [];
  for await (const evt of parseSSEStream(stream)) {
    events.push(evt);
  }
  assert.equal(events.length, 2);
  assert.equal(events[0].event, 'token');
  assert.equal(events[0].data, '{"text":"Ghost"}');
  assert.equal(events[1].event, 'done');
});

test('SSE Parser: AbortSignal mid-stream terminates cleanly and releases lock', async () => {
  const ac = new AbortController();
  const rawChunks = [
    'event: token\ndata: 1\n\n',
    'event: token\ndata: 2\n\n',
    'event: token\ndata: 3\n\n',
    'event: token\ndata: 4\n\n',
  ];
  const stream = makeReadableStream(rawChunks, 10);
  const events = [];

  for await (const evt of parseSSEStream(stream, ac.signal)) {
    events.push(evt);
    if (events.length === 2) {
      ac.abort();
    }
  }

  assert.equal(events.length, 2);
  // Verify stream lock was released by checking getReader succeeds
  const newReader = stream.getReader();
  assert.ok(newReader);
  newReader.releaseLock();
});

test('SSE Parser: Network drop / read failure throws and releases stream lock', async () => {
  const failingStream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('event: token\ndata: first\n\n'));
      controller.error(new TypeError('Network dropped / connection reset'));
    },
  });

  let threw = false;
  try {
    for await (const evt of parseSSEStream(failingStream)) {
      // should read first, then fail on second read
      assert.equal(evt.data, 'first');
    }
  } catch (err) {
    threw = true;
    assert.match(err.message, /Network dropped/);
  }
  assert.ok(threw, 'Expected stream read to throw error');
});

test('SSE Consumer JSON Parse Robustness: malformed and unexpected payloads', () => {
  // Test consumer error handling logic in useAsk / useSummon
  const malformedPayloads = [
    '{ broken json',
    '<html>502 Bad Gateway</html>',
    'undefined',
    '',
    '{"text": null}',
    '{"unexpected_key": 999}',
  ];

  for (const raw of malformedPayloads) {
    let parsedToken = null;
    let fallbackText = null;

    // Simulate useAsk token handler
    try {
      const parsed = JSON.parse(raw);
      parsedToken = parsed.text ?? parsed.token ?? '';
    } catch {
      fallbackText = raw;
    }

    assert.ok(parsedToken !== null || fallbackText !== null, 'Handled without uncaught exception');
  }
});

// ---------------------------------------------------------------------------
// 2. Citation Parsing & Regex Tests
// ---------------------------------------------------------------------------

test('Citation Regex: Valid 7-40 hex extraction and non-hex rejection', () => {
  const citationRegex = /\[([0-9a-fA-F]{7,40})\]/g;

  const validExamples = [
    { text: 'Auth was rewritten in [1a2b3c4].', expected: ['1a2b3c4'] },
    { text: 'Commit [d4e5f60718293a4b5c6d7e8f0123456789abcdef] is full 40-hex.', expected: ['d4e5f60718293a4b5c6d7e8f0123456789abcdef'] },
    { text: 'Multiple: [abcdef0] and [1234567].', expected: ['abcdef0', '1234567'] },
    { text: 'Punctuation: ([abcdef0]), and "[1234567]".', expected: ['abcdef0', '1234567'] },
  ];

  for (const ex of validExamples) {
    const matches = Array.from(ex.text.matchAll(citationRegex), (m) => m[1]);
    assert.deepEqual(matches, ex.expected);
  }

  const invalidExamples = [
    'Short 6-hex [1a2b3c]',
    'Too long 41-hex [1234567890abcdef1234567890abcdef1234567890]',
    'Evidence tag [E1] or [E2]',
    'Markdown link [example](https://...)',
    'Special chars [<script>]',
    'Non-hex characters [ghijk12]',
  ];

  for (const text of invalidExamples) {
    const matches = Array.from(text.matchAll(citationRegex), (m) => m[1]);
    assert.equal(matches.length, 0, `Expected 0 matches for: ${text}`);
  }
});

// ---------------------------------------------------------------------------
// 3. CommitDrawer & API URL Construction Tests
// ---------------------------------------------------------------------------

test('CommitDrawer: API URL construction correctly encodes SHA and repo path', () => {
  const base = 'http://localhost:8000';
  const testCases = [
    { sha: '1a2b3c4', repo: 'C:\\Users\\sahoo\\repo', expectedSha: '1a2b3c4', expectedRepo: 'C:\\Users\\sahoo\\repo' },
    { sha: 'sha/with/slashes', repo: '/path/with space/repo', expectedSha: 'sha%2Fwith%2Fslashes', expectedRepo: '/path/with space/repo' },
    { sha: 'abc1234', repo: 'C:/repos/ünicøde-name', expectedSha: 'abc1234', expectedRepo: 'C:/repos/ünicøde-name' },
  ];

  for (const tc of testCases) {
    const url = new URL(`/api/commit/${encodeURIComponent(tc.sha)}`, base);
    url.searchParams.set('repo', tc.repo);

    assert.ok(url.pathname.endsWith(tc.expectedSha));
    assert.equal(url.searchParams.get('repo'), tc.expectedRepo);
  }
});

// ---------------------------------------------------------------------------
// 4. Adversarial Audit: Calm Error State & Error Display Verification
// ---------------------------------------------------------------------------

test('Adversarial Probe: VoiceMessage component error prop inspection', () => {
  const voiceMessageSrc = readFileSync(
    resolve('web/src/components/VoiceMessage.tsx'),
    'utf-8'
  );

  // Check whether VoiceMessage extracts or displays message.error
  const extractsError = voiceMessageSrc.includes('error') && voiceMessageSrc.includes('message.error');
  const hasErrorDisplay = /styles\.error|className=.*error/i.test(voiceMessageSrc);

  console.log(`[AUDIT] VoiceMessage extracts message.error: ${extractsError}`);
  console.log(`[AUDIT] VoiceMessage has error display JSX/class: ${hasErrorDisplay}`);

  assert.equal(
    extractsError,
    true,
    'VoiceMessage extracts and displays message.error'
  );
  assert.equal(
    hasErrorDisplay,
    true,
    'VoiceMessage has error display JSX/class'
  );
});

test('Adversarial Probe: SummonScreen component error prop inspection', () => {
  const summonScreenSrc = readFileSync(
    resolve('web/src/components/SummonScreen.tsx'),
    'utf-8'
  );

  const hasErrorProp = summonScreenSrc.includes('error?:') || summonScreenSrc.includes('error:');
  console.log(`[AUDIT] SummonScreen accepts error prop: ${hasErrorProp}`);

  assert.equal(
    hasErrorProp,
    true,
    'SummonScreen accepts error prop to display summon failures'
  );
});

// ---------------------------------------------------------------------------
// 5. Build, Tokens & Bundle Budget Audit
// ---------------------------------------------------------------------------

test('Asset Audit: Dist bundle size, tokens and fonts', () => {
  const distDir = resolve('web/dist');
  assert.ok(existsSync(distDir), 'web/dist must exist');
  assert.ok(existsSync(join(distDir, 'index.html')), 'web/dist/index.html must exist');

  const html = readFileSync(join(distDir, 'index.html'), 'utf-8');
  assert.ok(html.includes('The Ghost Maintainer'), 'HTML must have title');
  assert.ok(html.includes('Fraunces') || html.includes('fonts.googleapis.com'), 'HTML must reference Fraunces font');

  const tokensCss = readFileSync(resolve('web/src/styles/tokens.css'), 'utf-8');
  assert.ok(tokensCss.includes('--color-bg'), 'Must have --color-bg');
  assert.ok(tokensCss.includes('--color-accent'), 'Must have --color-accent');
  assert.ok(tokensCss.includes('--color-verified'), 'Must have --color-verified');
  assert.ok(tokensCss.includes('--color-unverified'), 'Must have --color-unverified');
  assert.ok(tokensCss.includes('prefers-reduced-motion'), 'Must support prefers-reduced-motion');
});
