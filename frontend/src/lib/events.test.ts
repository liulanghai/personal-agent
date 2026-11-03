import { describe, expect, it } from 'vitest';
import type { AgentEvent } from '@personal-agent/sdk';
import { contextManifest, isTerminal, toolSteps } from './events';

let sequence = 0;
function event(type: string, data: Record<string, unknown> = {}): AgentEvent {
  sequence += 1;
  return {
    id: `e${sequence}`,
    sequence,
    run_id: 'r1',
    type,
    data,
    created_at: '2026-11-03T00:00:00Z',
  };
}

describe('toolSteps', () => {
  it('pairs started and completed events by tool_call_id, in start order', () => {
    const steps = toolSteps([
      event('tool_call.started', {
        tool_call_id: 'a',
        tool_name: 'read_file',
        arguments: { p: 1 },
      }),
      event('tool_call.started', { tool_call_id: 'b', tool_name: 'write_file', arguments: {} }),
      event('tool_call.completed', { tool_call_id: 'b', status: 'failed', result: 'denied' }),
      event('tool_call.completed', { tool_call_id: 'a', status: 'succeeded', result: 'ok' }),
    ]);

    expect(steps.map((s) => [s.name, s.status, s.result])).toEqual([
      ['read_file', 'succeeded', 'ok'],
      ['write_file', 'failed', 'denied'],
    ]);
    expect(steps[0].arguments).toEqual({ p: 1 });
  });

  it('marks a step without a completed event as running', () => {
    const steps = toolSteps([
      event('tool_call.started', { tool_call_id: 'a', tool_name: 'list_files' }),
    ]);

    expect(steps).toHaveLength(1);
    expect(steps[0].status).toBe('running');
    expect(steps[0].result).toBeUndefined();
  });

  it('ignores unrelated events', () => {
    expect(toolSteps([event('run.started'), event('message.delta', { delta: 'hi' })])).toEqual([]);
  });
});

describe('contextManifest', () => {
  it('returns the data of the context.built event', () => {
    const manifest = { instructions: ['AGENTS.md'] };
    expect(contextManifest([event('run.started'), event('context.built', manifest)])).toEqual(
      manifest,
    );
  });

  it('is undefined before the context is built', () => {
    expect(contextManifest([event('run.started')])).toBeUndefined();
  });
});

describe('isTerminal', () => {
  it.each(['run.completed', 'run.failed', 'run.cancelled'])('%s ends a run', (type) => {
    expect(isTerminal(event(type))).toBe(true);
  });

  it.each(['run.started', 'message.delta', 'tool_call.completed'])('%s does not', (type) => {
    expect(isTerminal(event(type))).toBe(false);
  });
});
