import { describe, expect, it } from 'vitest';
import type { AgentEvent } from '@personal-agent/sdk';
import { buildTimeline, isComplete, isTerminal } from './timeline';

const NOW = '2026-11-04T08:00:00Z';
let sequence = 0;

function event(type: string, data: Record<string, unknown> = {}): AgentEvent {
  sequence += 1;
  return { id: `e${sequence}`, sequence, run_id: 'r1', type, data, created_at: NOW };
}

function delta(text: string): AgentEvent {
  return event('message.delta', { delta: text });
}

function started(id: string, name: string, args: unknown = {}): AgentEvent {
  return event('tool_call.started', { tool_call_id: id, tool_name: name, arguments: args });
}

function completed(id: string, status: string, result: unknown = null): AgentEvent {
  return event('tool_call.completed', { tool_call_id: id, status, result });
}

describe('buildTimeline', () => {
  it('merges consecutive deltas into one text item', () => {
    const items = buildTimeline([delta('你'), delta('好')]);

    expect(items).toEqual([{ kind: 'text', id: expect.any(String), text: '你好' }]);
  });

  it('keeps the loop order of text, tool calls and skills', () => {
    const items = buildTimeline([
      event('run.started'),
      event('context.built', { instructions: ['AGENTS.md'] }),
      delta('先读文件'),
      started('t1', 'read_file', { path: 'a.md' }),
      completed('t1', 'succeeded', { content: 'x' }),
      delta('再读技能'),
      started('t2', 'read_skill'),
      completed('t2', 'succeeded'),
      delta('完成'),
      event('run.completed'),
    ]);

    expect(items.map((i) => (i.kind === 'tool' ? `tool:${i.name}` : i.kind))).toEqual([
      'context',
      'text',
      'tool:read_file',
      'text',
      'tool:read_skill',
      'text',
      'end',
    ]);
    expect(items[2]).toMatchObject({
      status: 'succeeded',
      arguments: { path: 'a.md' },
      result: { content: 'x' },
    });
  });

  it('pairs a completion with its call even when calls overlap', () => {
    const items = buildTimeline([
      started('t1', 'read_file'),
      started('t2', 'list_files'),
      completed('t2', 'succeeded'),
    ]);

    expect(items).toMatchObject([
      { kind: 'tool', name: 'read_file', status: 'running' },
      { kind: 'tool', name: 'list_files', status: 'succeeded' },
    ]);
  });

  it('marks failed tool calls', () => {
    const items = buildTimeline([started('t1', 'shell'), completed('t1', 'failed')]);

    expect(items).toMatchObject([{ kind: 'tool', status: 'failed' }]);
  });

  it('keeps unknown event types as generic items', () => {
    const items = buildTimeline([delta('a'), event('plan.updated', { steps: 2 }), delta('b')]);

    expect(items).toMatchObject([
      { kind: 'text', text: 'a' },
      { kind: 'event', type: 'plan.updated', data: { steps: 2 } },
      { kind: 'text', text: 'b' },
    ]);
  });

  it('does not mistake inherited object keys for terminal events', () => {
    for (const type of ['constructor', 'toString', '__proto__']) {
      const unknown = event(type, { value: 1 });
      expect(isTerminal(unknown)).toBe(false);
      expect(buildTimeline([unknown])).toMatchObject([{ kind: 'event', type, data: { value: 1 } }]);
    }
  });

  it('records how the run ended', () => {
    expect(buildTimeline([event('run.failed', { error: 'boom' })])).toMatchObject([
      { kind: 'end', status: 'failed', error: 'boom' },
    ]);
    expect(buildTimeline([event('run.cancelled')])).toMatchObject([
      { kind: 'end', status: 'cancelled' },
    ]);
  });
});

describe('isComplete / isTerminal', () => {
  it('is complete only once the stream reached a terminal event', () => {
    expect(isComplete(buildTimeline([delta('a')]))).toBe(false);
    expect(isComplete(buildTimeline([delta('a'), event('run.completed')]))).toBe(true);
  });

  it('recognises the three terminal events', () => {
    expect(isTerminal(event('run.completed'))).toBe(true);
    expect(isTerminal(event('run.failed'))).toBe(true);
    expect(isTerminal(event('run.cancelled'))).toBe(true);
    expect(isTerminal(event('message.delta'))).toBe(false);
  });
});
