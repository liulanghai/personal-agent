import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentEvent, Message, Run } from '@personal-agent/sdk';
import { App } from './App';

// The whole app talks to the backend through this one module; tests script it.
const client = vi.hoisted(() => ({
  conversations: { list: vi.fn(), create: vi.fn() },
  messages: { list: vi.fn(), send: vi.fn() },
  runs: { list: vi.fn(), cancel: vi.fn(), events: vi.fn() },
  skills: { list: vi.fn(), get: vi.fn() },
  settings: { get: vi.fn(), save: vi.fn() },
  discovery: vi.fn(),
  files: { upload: vi.fn(), artifacts: vi.fn(), content: vi.fn() },
}));
vi.mock('./api/client', () => ({ client }));

const NOW = '2026-11-03T08:00:00Z';

function message(id: string, role: Message['role'], content: string): Message {
  return { id, conversation_id: 'c1', role, content, run_id: 'r1', created_at: NOW };
}

function completedRun(): Run {
  return {
    id: 'r1',
    conversation_id: 'c1',
    status: 'completed',
    skill_id: null,
    file_ids: [],
    error: null,
    created_at: NOW,
    updated_at: NOW,
  };
}

function event(id: string, type: string, data: Record<string, unknown> = {}): AgentEvent {
  return { id, sequence: Number(id), run_id: 'r1', type, data, created_at: NOW };
}

async function* replay(events: AgentEvent[]) {
  yield* events;
}

beforeEach(() => {
  vi.clearAllMocks();
  client.conversations.list.mockResolvedValue({
    items: [{ id: 'c1', title: '周报讨论', created_at: NOW }],
  });
  client.skills.list.mockResolvedValue({ items: [] });
  client.settings.get.mockResolvedValue({
    base_url: 'https://api.example.com/v1',
    model: 'test-model',
    has_api_key: false,
    timezone: 'Asia/Shanghai',
    instruction_mode: 'auto',
    workspace_path: '/tmp/workspace',
  });
  client.discovery.mockResolvedValue({ instructions: [], warnings: [] });
  client.files.artifacts.mockResolvedValue({ items: [] });
});

describe('App', () => {
  it('starts on the welcome screen with the configured model', async () => {
    render(<App />);

    expect(await screen.findByText('test-model')).toBeTruthy();
    expect(screen.getByText('读懂一份文档')).toBeTruthy();
    expect(screen.getByText('周报讨论')).toBeTruthy();
  });

  it('navigates to the settings page', async () => {
    render(<App />);
    await screen.findByText('test-model');

    await userEvent.click(screen.getByRole('button', { name: /设置与模型/ }));

    expect(screen.getByText('连接你的模型。')).toBeTruthy();
    expect(await screen.findByText(/未发现规则文件/)).toBeTruthy();
  });

  it('opens a conversation and replays its finished run', async () => {
    const messages = {
      items: [message('m1', 'user', '写周报'), message('m2', 'assistant', '周报已生成')],
    };
    client.messages.list.mockResolvedValue(messages);
    // A fresh object per call, like JSON from a real server: a refresh must not
    // look like a new run to the event subscription.
    client.runs.list.mockImplementation(async () => ({ items: [completedRun()] }));
    client.runs.events.mockImplementation(() =>
      replay([
        event('1', 'context.built', { instructions: [] }),
        event('2', 'tool_call.started', { tool_call_id: 't1', tool_name: 'read_file' }),
        event('3', 'tool_call.completed', { tool_call_id: 't1', status: 'succeeded' }),
        event('4', 'run.completed'),
      ]),
    );
    render(<App />);

    await userEvent.click(await screen.findByRole('button', { name: '周报讨论' }));

    expect(await screen.findByText('周报已生成')).toBeTruthy();
    const execution = await screen.findByText(/执行过程 · 1 次工具调用/);
    expect(within(execution).getByText('已完成')).toBeTruthy();
    expect(screen.getByText('read_file')).toBeTruthy();
    expect(screen.getByRole('button', { name: '查看本次上下文与环境信息' })).toBeTruthy();
    // The stream is opened once per run, from the beginning.
    expect(client.runs.events).toHaveBeenCalledTimes(1);
    expect(client.runs.events.mock.calls[0].slice(0, 2)).toEqual(['r1', undefined]);
  });
});
