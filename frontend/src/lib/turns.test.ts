import { describe, expect, it } from 'vitest';
import type { AgentFile, Message } from '@personal-agent/sdk';
import { groupTurns } from './turns';

const NOW = '2026-11-03T00:00:00Z';

function message(id: string, role: Message['role'], runId: string): Message {
  return { id, conversation_id: 'c1', role, content: id, run_id: runId, created_at: NOW };
}

function artifact(id: string, runId: string | null): AgentFile {
  return {
    id,
    name: `${id}.md`,
    path: `reports/${id}.md`,
    kind: 'artifact',
    run_id: runId,
    size: 10,
    created_at: NOW,
  };
}

describe('groupTurns', () => {
  it('groups prompts, replies and artifacts by run, in conversation order', () => {
    const turns = groupTurns(
      [
        message('u1', 'user', 'r1'),
        message('a1', 'assistant', 'r1'),
        message('u2', 'user', 'r2'),
        message('a2', 'assistant', 'r2'),
      ],
      [artifact('f2', 'r2'), artifact('f1', 'r1')],
    );

    expect(turns.map((t) => t.runId)).toEqual(['r1', 'r2']);
    expect(turns[0].prompts.map((m) => m.id)).toEqual(['u1']);
    expect(turns[0].replies.map((m) => m.id)).toEqual(['a1']);
    expect(turns[0].artifacts.map((f) => f.id)).toEqual(['f1']);
    expect(turns[1].artifacts.map((f) => f.id)).toEqual(['f2']);
  });

  it('keeps a turn for a running run that has no reply yet', () => {
    const turns = groupTurns([message('u1', 'user', 'r1')], [], 'r1');

    expect(turns).toHaveLength(1);
    expect(turns[0].replies).toEqual([]);
  });

  it('adds a turn for the latest run before its messages are loaded', () => {
    const turns = groupTurns([message('u1', 'user', 'r1')], [], 'r2');

    expect(turns.map((t) => t.runId)).toEqual(['r1', 'r2']);
  });

  it('ignores files without a run', () => {
    const upload: AgentFile = { ...artifact('up', null), kind: 'upload' };
    expect(groupTurns([message('u1', 'user', 'r1')], [upload])[0].artifacts).toEqual([]);
  });
});
