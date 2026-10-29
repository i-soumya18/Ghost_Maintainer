import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Emulate browser window environment for URL resolution
if (typeof globalThis.window === 'undefined') {
  globalThis.window = {
    location: {
      href: 'http://localhost:8000/',
    },
  };
}

// Import real production API functions from web/src/api.ts
import { askQuestionStream, summonRepoStream } from '../web/src/api.ts';

// Helper to simulate fetch returning a ReadableStream
function mockFetchWithStream(stream, headers = { 'content-type': 'text/event-stream' }, ok = true, status = 200) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    if (!ok) {
      return {
        ok: false,
        status,
        statusText: 'Internal Server Error',
        text: async () => 'Database connection failed',
        headers: new Headers(headers),
      };
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers(headers),
      body: stream,
    };
  };
  return () => {
    globalThis.fetch = originalFetch;
  };
}

// ---------------------------------------------------------------------------
// Test Suite 1: Adversarial SSE Boundary & Encoding Stress Tests
// ---------------------------------------------------------------------------

test('Adversarial SSE: Boundary split directly across CRLF characters', async () => {
  // Test split between \r and \n across chunks
  const chunks = [
    'event: token\r',
    '\ndata: {"text":"gh',
    'ost"}\r',
    '\n\r',
    '\nevent: done\r\ndata: {}\r\n\r\n'
  ];

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const c of chunks) {
        controller.enqueue(encoder.encode(c));
      }
      controller.close();
    }
  });

  const restoreFetch = mockFetchWithStream(stream);
  try {
    const events = [];
    for await (const evt of askQuestionStream({ question: 'test', repo: 'dummy' })) {
      events.push(evt);
    }
    assert.equal(events.length, 2, 'Should receive 2 events despite split CRLF boundaries');
    assert.equal(events[0].event, 'token');
    assert.equal(events[0].data, '{"text":"ghost"}');
    assert.equal(events[1].event, 'done');
  } finally {
    restoreFetch();
  }
});

test('Adversarial SSE: Multi-byte UTF-8 split across byte boundaries', async () => {
  // Candle glyph 🕯 is UTF-8 [0xF0, 0x9F, 0x94, 0xAF] (4 bytes)
  const fullText = 'event: token\r\ndata: {"candle":"🕯"}\r\n\r\n';
  const fullBytes = new TextEncoder().encode(fullText);

  const stream = new ReadableStream({
    start(controller) {
      // Send 1 byte at a time to forcefully split multi-byte UTF-8 sequences
      for (let i = 0; i < fullBytes.length; i++) {
        controller.enqueue(fullBytes.subarray(i, i + 1));
      }
      controller.close();
    }
  });

  const restoreFetch = mockFetchWithStream(stream);
  try {
    const events = [];
    for await (const evt of askQuestionStream({ question: 'test', repo: 'dummy' })) {
      events.push(evt);
    }
    assert.equal(events.length, 1);
    const parsed = JSON.parse(events[0].data);
    assert.equal(parsed.candle, '🕯', 'Multi-byte UTF-8 was correctly reassembled');
  } finally {
    restoreFetch();
  }
});

test('Adversarial SSE: Multi-line data fields with CRLF normalization', async () => {
  const payload = 'event: citation\r\ndata: line 1\r\ndata: line 2\r\ndata: line 3\r\n\r\n';
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload));
      controller.close();
    }
  });

  const restoreFetch = mockFetchWithStream(stream);
  try {
    const events = [];
    for await (const evt of askQuestionStream({ question: 'test', repo: 'dummy' })) {
      events.push(evt);
    }
    assert.equal(events.length, 1);
    assert.equal(events[0].event, 'citation');
    assert.equal(events[0].data, 'line 1\nline 2\nline 3');
  } finally {
    restoreFetch();
  }
});

test('Adversarial SSE: Stream closed with single newline (missing second empty delimiter) flushes last event', async () => {
  // Proxy terminates after data line with single \r\n, missing the terminating empty line
  const payload = 'event: token\r\ndata: {"text":"final token"}\r\n';
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload));
      controller.close();
    }
  });

  const restoreFetch = mockFetchWithStream(stream);
  try {
    const events = [];
    for await (const evt of askQuestionStream({ question: 'test', repo: 'dummy' })) {
      events.push(evt);
    }
    assert.equal(events.length, 1, 'Trailing event without second delimiter must still flush');
    assert.equal(events[0].data, '{"text":"final token"}');
  } finally {
    restoreFetch();
  }
});

test('Adversarial SSE: Truncated line without newline is not dispatched as corrupt event', async () => {
  // Stream truncated mid-wire without even a newline character
  const payload = 'event: token\r\ndata: {"text":"truncated';
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload));
      controller.close();
    }
  });

  const restoreFetch = mockFetchWithStream(stream);
  try {
    const events = [];
    for await (const evt of askQuestionStream({ question: 'test', repo: 'dummy' })) {
      events.push(evt);
    }
    assert.equal(events.length, 0, 'Incomplete, un-delimited line is not dispatched as valid SSE');
  } finally {
    restoreFetch();
  }
});

test('Adversarial SSE: Mixed LF and CRLF in single stream', async () => {
  const payload = 'event: token\ndata: {"first":1}\n\nevent: token\r\ndata: {"second":2}\r\n\r\n';
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload));
      controller.close();
    }
  });

  const restoreFetch = mockFetchWithStream(stream);
  try {
    const events = [];
    for await (const evt of askQuestionStream({ question: 'test', repo: 'dummy' })) {
      events.push(evt);
    }
    assert.equal(events.length, 2);
    assert.equal(events[0].data, '{"first":1}');
    assert.equal(events[1].data, '{"second":2}');
  } finally {
    restoreFetch();
  }
});

// ---------------------------------------------------------------------------
// Test Suite 2: Network Drops, Severed Connections & Abort Handling
// ---------------------------------------------------------------------------

test('Network Drop: Fetch throws TypeError (e.g. Offline / DNS failure)', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new TypeError('Failed to fetch');
  };

  try {
    await assert.rejects(
      async () => {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        for await (const _ of askQuestionStream({ question: 'test', repo: 'dummy' })) {}
      },
      /Failed to fetch/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Network Drop: Mid-stream disconnect throws and releases stream reader lock', async () => {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('event: token\r\ndata: chunk1\r\n\r\n'));
      setTimeout(() => {
        controller.error(new Error('Connection severed by remote peer'));
      }, 5);
    }
  });

  const restoreFetch = mockFetchWithStream(stream);
  try {
    let receivedCount = 0;
    await assert.rejects(
      async () => {
        for await (const evt of askQuestionStream({ question: 'test', repo: 'dummy' })) {
          receivedCount++;
          assert.equal(evt.data, 'chunk1');
        }
      },
      /Connection severed by remote peer/
    );
    assert.equal(receivedCount, 1, 'Should have received first event before disconnect');
    // Verify stream lock was freed
    const reader = stream.getReader();
    assert.ok(reader);
    reader.releaseLock();
  } finally {
    restoreFetch();
  }
});

test('AbortSignal: Immediate abort does not hang and terminates cleanly', async () => {
  const ac = new AbortController();
  ac.abort();

  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('event: token\r\ndata: should not read\r\n\r\n'));
      controller.close();
    }
  });

  const restoreFetch = mockFetchWithStream(stream);
  try {
    const events = [];
    for await (const evt of askQuestionStream({ question: 'test', repo: 'dummy', signal: ac.signal })) {
      events.push(evt);
    }
    assert.equal(events.length, 0, 'No events yielded when signal is pre-aborted');
  } finally {
    restoreFetch();
  }
});

test('Summon Repo Stream: handles application/json immediate response', async () => {
  const jsonPayload = JSON.stringify({ name: 'test-repo', path: '/code/test', commit_count: 42 });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    return {
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => JSON.parse(jsonPayload),
    };
  };

  try {
    const events = [];
    for await (const evt of summonRepoStream({ repo: '/code/test' })) {
      events.push(evt);
    }
    assert.equal(events.length, 1);
    assert.equal(events[0].event, 'done');
    assert.equal(events[0].data, jsonPayload);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Summon Repo Stream: HTTP 500 throws descriptive error', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    return {
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: async () => 'Repository not found or corrupted git tree',
    };
  };

  try {
    await assert.rejects(
      async () => {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        for await (const _ of summonRepoStream({ repo: 'invalid' })) {}
      },
      /Summon failed: Repository not found or corrupted git tree/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

// ---------------------------------------------------------------------------
// Test Suite 3: VoiceMessage & SummonScreen Calm Error State Verification
// ---------------------------------------------------------------------------

test('Adversarial UI State Audit: VoiceMessage calm error branch structure', () => {
  const src = readFileSync(resolve('web/src/components/VoiceMessage.tsx'), 'utf-8');

  // Verify that error condition is evaluated before empty string or normal render
  const errorConditionRegex = /if\s*\(\s*message\.error\s*\|\|\s*streamPhase\s*===\s*['"]error['"]\s*\)/;
  assert.ok(errorConditionRegex.test(src), 'VoiceMessage must check (message.error || streamPhase === "error")');

  // Verify role="alert"
  assert.ok(src.includes('role="alert"'), 'Must have role="alert" for accessibility');

  // Verify calm heading
  assert.ok(src.includes('The séance connection was severed'), 'Must display calm severed connection heading');

  // Verify fallback error message
  assert.ok(
    src.includes('The spirits fell silent unexpectedly. Please inquire again.'),
    'Must provide calm actionable fallback when error message is empty'
  );

  // Verify that styles classes are used
  assert.ok(src.includes('styles.errorContent'), 'Must use styles.errorContent');
  assert.ok(src.includes('styles.errorHeader'), 'Must use styles.errorHeader');
  assert.ok(src.includes('styles.errorIcon'), 'Must use styles.errorIcon');
  assert.ok(src.includes('styles.errorText'), 'Must use styles.errorText');
});

test('Adversarial UI State Audit: SummonScreen error banner prop & structure', () => {
  const src = readFileSync(resolve('web/src/components/SummonScreen.tsx'), 'utf-8');

  // Verify SummonScreenProps includes error?: string | null
  assert.ok(/error\?:\s*string\s*\|\s*null/.test(src), 'SummonScreenProps must define error?: string | null');

  // Verify error banner rendered
  assert.ok(src.includes('styles.errorBanner'), 'SummonScreen must reference styles.errorBanner');
  assert.ok(src.includes('role="alert"'), 'SummonScreen must use role="alert" for errors');

  // Verify CSS module defines .errorBanner
  const css = readFileSync(resolve('web/src/components/SummonScreen.module.css'), 'utf-8');
  assert.ok(css.includes('.errorBanner'), 'SummonScreen.module.css must define .errorBanner');
  assert.ok(css.includes('--color-error'), 'errorBanner must reference --color-error');
  assert.ok(css.includes('--color-error-bg'), 'errorBanner must reference --color-error-bg');
});

test('Adversarial UI State Audit: App.tsx wires summonState.error and askState.error', () => {
  const appSrc = readFileSync(resolve('web/src/App.tsx'), 'utf-8');

  // Verify summonState.error passed to SummonScreen
  assert.ok(appSrc.includes('error={summonState.error}'), 'App.tsx must pass summonState.error to SummonScreen');

  // Verify askState error updates messages
  assert.ok(appSrc.includes('error: askState.error ?? undefined'), 'App.tsx must set message.error from askState.error');
  assert.ok(appSrc.includes('streamPhase: askState.phase'), 'App.tsx must set streamPhase from askState.phase');
});

// ---------------------------------------------------------------------------
// Test Suite 4: CSS Tokens & Design Palette Completeness
// ---------------------------------------------------------------------------

test('Adversarial Design Token Audit: Error colors and typography exist and contrast', () => {
  const tokensCss = readFileSync(resolve('web/src/styles/tokens.css'), 'utf-8');
  assert.ok(tokensCss.includes('--color-error:'), 'Must define --color-error');
  assert.ok(tokensCss.includes('--color-error-bg:'), 'Must define --color-error-bg');
  assert.ok(tokensCss.includes('--font-voice:'), 'Must define --font-voice');
  assert.ok(tokensCss.includes('--font-ui:'), 'Must define --font-ui');
});

// ---------------------------------------------------------------------------
// Test Suite 5: React Component Empirical SSR Rendering Tests
// ---------------------------------------------------------------------------

import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const esbuild = require('../web/node_modules/esbuild');
const React = require('../web/node_modules/react');
const ReactDOMServer = require('../web/node_modules/react-dom/server');
const jsxRuntime = require('../web/node_modules/react/jsx-runtime');

function loadComponent(entryPath, componentName) {
  const bundle = esbuild.buildSync({
    entryPoints: [entryPath],
    bundle: true,
    write: false,
    format: 'cjs',
    loader: { '.module.css': 'empty', '.css': 'empty' },
    external: ['react', 'react-dom', 'react/jsx-runtime'],
  });

  const moduleObj = { exports: {} };
  const fn = new Function('module', 'exports', 'require', bundle.outputFiles[0].text);
  fn(moduleObj, moduleObj.exports, (mod) => {
    if (mod === 'react') return React;
    if (mod === 'react-dom') return ReactDOMServer;
    if (mod === 'react/jsx-runtime') return jsxRuntime;
    return require(mod);
  });
  return moduleObj.exports[componentName];
}

test('SSR: VoiceMessage renders severed connection alert with message.error', () => {
  const VoiceMessage = loadComponent(resolve('web/src/components/VoiceMessage.tsx'), 'VoiceMessage');
  const msg = {
    id: 'test-severed',
    role: 'assistant',
    text: '',
    evidence: [],
    streamPhase: 'error',
    error: 'Remote server forcibly closed connection',
    timestamp: new Date(),
  };

  const html = ReactDOMServer.renderToString(React.createElement(VoiceMessage, { message: msg }));

  assert.ok(html.includes('role="alert"'), 'Rendered HTML must have role="alert"');
  assert.ok(html.includes('The séance connection was severed'), 'Must contain severed connection heading');
  assert.ok(html.includes('Remote server forcibly closed connection'), 'Must contain specific error text');
  assert.ok(!html.includes('class="bubble"></'), 'Must not render an empty bubble');
  assert.ok(html.length > 150, 'Rendered HTML must be substantial, not empty');
});

test('SSR: VoiceMessage renders calm fallback when error text is absent', () => {
  const VoiceMessage = loadComponent(resolve('web/src/components/VoiceMessage.tsx'), 'VoiceMessage');
  const msg = {
    id: 'test-fallback',
    role: 'assistant',
    text: '',
    evidence: [],
    streamPhase: 'error',
    timestamp: new Date(),
  };

  const html = ReactDOMServer.renderToString(React.createElement(VoiceMessage, { message: msg }));

  assert.ok(html.includes('role="alert"'), 'Rendered HTML must have role="alert"');
  assert.ok(html.includes('The séance connection was severed'), 'Must contain severed connection heading');
  assert.ok(
    html.includes('The spirits fell silent unexpectedly. Please inquire again.'),
    'Must contain calm actionable fallback prompt'
  );
});

test('SSR: VoiceMessage normal streaming does not render error alert', () => {
  const VoiceMessage = loadComponent(resolve('web/src/components/VoiceMessage.tsx'), 'VoiceMessage');
  const msg = {
    id: 'test-streaming',
    role: 'assistant',
    text: 'Speaking of commit [1a2b3c4]...',
    evidence: [],
    streamPhase: 'streaming',
    timestamp: new Date(),
  };

  const html = ReactDOMServer.renderToString(React.createElement(VoiceMessage, { message: msg }));

  assert.ok(!html.includes('role="alert"'), 'Normal message must not have role="alert"');
  assert.ok(!html.includes('The séance connection was severed'), 'Normal message must not claim connection was severed');
  assert.ok(html.includes('Voices are fiction.'), 'Assistant message must have disclaimer footer');
});

test('SSR: SummonScreen renders errorBanner role="alert" when error is present', () => {
  const SummonScreen = loadComponent(resolve('web/src/components/SummonScreen.tsx'), 'SummonScreen');

  const html = ReactDOMServer.renderToString(React.createElement(SummonScreen, {
    onSummon: () => {},
    knownRepos: [],
    error: 'Repository path not found: C:/fake/repo',
  }));

  assert.ok(html.includes('role="alert"'), 'Error banner must have role="alert"');
  assert.ok(html.includes('Repository path not found: C:/fake/repo'), 'Must display error string');
});

test('SSR: SummonScreen suppresses errorBanner when error is null', () => {
  const SummonScreen = loadComponent(resolve('web/src/components/SummonScreen.tsx'), 'SummonScreen');

  const html = ReactDOMServer.renderToString(React.createElement(SummonScreen, {
    onSummon: () => {},
    knownRepos: [],
    error: null,
  }));

  assert.ok(!html.includes('role="alert"'), 'Must not render alert banner when error is null');
});
