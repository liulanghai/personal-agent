import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentEvent, Message, Run } from '@personal-agent/sdk';
import { App } from './App';

// The whole app talks to the backend through this one module; tests script it.
const client = vi.hoisted(() => ({
  conversations: { list: vi.fn(), create: vi.fn() },
  messages: { list: vi.fn(), send: vi.fn() },
  runs: { list: vi.fn(), cancel: vi.fn(), events: vi.fn(), get: vi.fn(), modelCalls: vi.fn() },
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

  it('waits for saved settings before mounting the editable recording switch', async () => {
    let resolveSettings!: (value: object) => void;
    client.settings.get.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSettings = resolve;
        }),
    );
    render(<App />);
    await userEvent.click(screen.getByRole('button', { name: /设置与模型/ }));
    expect(await screen.findByText('正在加载模型设置…')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '保存配置' })).toBeNull();
    resolveSettings({ model: 'm', base_url: 'https://example.com', record_model_calls: true });
    const checkbox = await screen.findByRole('checkbox', { name: /保存完整模型交互/ });
    expect((checkbox as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText(/包含对话和文件正文/)).toBeTruthy();
    client.settings.save.mockImplementation(async (settings) => settings);
    await userEvent.click(checkbox);
    await userEvent.click(screen.getByRole('button', { name: '保存配置' }));
    expect(client.settings.save).toHaveBeenCalledWith(
      expect.objectContaining({ record_model_calls: false, api_key: null }),
    );
    expect(await screen.findByText('配置已保存')).toBeTruthy();
  });

  it('keeps model records accessible in each historical turn after loading a conversation', async () => {
    client.messages.list.mockResolvedValue({
      items: [
        { ...message('old', 'user', '上轮问题'), run_id: 'old-run' },
        message('latest', 'user', '本轮问题'),
      ],
    });
    client.runs.list.mockResolvedValue({ items: [completedRun()] });
    client.runs.events.mockImplementation(() => replay([event('1', 'run.completed')]));
    client.runs.get.mockResolvedValue(completedRun());
    client.runs.modelCalls.mockResolvedValue({ items: [] });
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: '周报讨论' }));
    await waitFor(() => expect(client.messages.list).toHaveBeenCalledTimes(2));
    const entries = screen.getAllByText('模型调用');
    expect(entries).toHaveLength(2);
    expect(client.runs.modelCalls).not.toHaveBeenCalled();
    // The older run is absent from runs.list, and has no saved assistant text.
    // Its ID still comes from the turn, so both record panels remain reachable.
    for (const [index, runId] of ['old-run', 'r1'].entries()) {
      const panel = entries[index].closest('details')!;
      expect(panel.open).toBe(false);
      expect(panel.textContent).not.toContain('0 次工具调用');
      await userEvent.click(entries[index]);
      expect(await within(panel).findByText(/开启前的调用无法补录/)).toBeTruthy();
      expect(client.runs.modelCalls).toHaveBeenNthCalledWith(index + 1, runId);
    }
  });

  it('replays a finished run in the order the loop produced it, inside the reply', async () => {
    const saved = '先读一下文件\n\n再看看技能\n\n周报已生成';
    client.messages.list.mockResolvedValue({
      items: [message('m1', 'user', '写周报'), message('m2', 'assistant', saved)],
    });
    // A fresh object per call, like JSON from a real server: a refresh must not
    // look like a new run to the event subscription.
    client.runs.list.mockImplementation(async () => ({ items: [completedRun()] }));
    client.files.artifacts.mockResolvedValue({
      items: [
        {
          id: 'f1',
          name: 'weekly.md',
          path: 'reports/weekly.md',
          kind: 'artifact',
          run_id: 'r1',
          size: 2048,
          created_at: NOW,
        },
      ],
    });
    // Text, tool calls, a skill and an event type the UI has never seen, interleaved.
    client.runs.events.mockImplementation(() =>
      replay([
        event('1', 'run.started'),
        event('2', 'context.built', { instructions: ['AGENTS.md'] }),
        event('3', 'message.delta', { delta: '先读一下' }),
        event('4', 'message.delta', { delta: '文件' }),
        event('5', 'tool_call.started', { tool_call_id: 't1', tool_name: 'read_file' }),
        event('6', 'tool_call.completed', { tool_call_id: 't1', status: 'succeeded' }),
        event('7', 'message.delta', { delta: '再看看技能' }),
        event('8', 'tool_call.started', { tool_call_id: 't2', tool_name: 'read_skill' }),
        event('9', 'tool_call.completed', { tool_call_id: 't2', status: 'failed' }),
        event('10', 'plan.updated', { steps: 2 }),
        event('11', 'message.delta', { delta: '周报已生成' }),
        event('12', 'run.completed'),
      ]),
    );
    render(<App />);

    await userEvent.click(await screen.findByRole('button', { name: '周报讨论' }));

    // The saved reply renders first; wait for a step only the event timeline has.
    await screen.findByText('plan.updated');
    await waitFor(() => expect(client.messages.list).toHaveBeenCalledTimes(2));
    const reply = screen.getByText('plan.updated').closest<HTMLElement>('.message.assistant')!;
    // Everything the run produced sits inside the agent's reply, after the prompt.
    expect(isBefore(screen.getByText('写周报'), reply)).toBe(true);
    const parts = Array.from(
      reply.querySelectorAll(
        '.message-body > p, .message-body > .step > summary, .artifact strong',
      ),
      (el) => el.textContent,
    );
    expect(parts).toEqual([
      expect.stringContaining('构建上下文'),
      '先读一下文件',
      expect.stringContaining('read_file'),
      '再看看技能',
      expect.stringContaining('read_skill'),
      expect.stringContaining('plan.updated'),
      '周报已生成',
      expect.stringContaining('模型调用'),
      'weekly.md',
    ]);
    expect(within(reply).getByText('失败')).toBeTruthy();
    // The timeline replaces the saved text; it is not shown twice.
    expect(screen.getAllByText('周报已生成')).toHaveLength(1);
    // The stream is opened once per run, from the beginning.
    expect(client.runs.events).toHaveBeenCalledTimes(1);
    expect(client.runs.events.mock.calls[0].slice(0, 2)).toEqual(['r1', undefined]);
  });

  it('falls back to the saved reply when the stream did not reach the end', async () => {
    client.messages.list.mockResolvedValue({
      items: [message('m1', 'user', '写周报'), message('m2', 'assistant', '周报已生成')],
    });
    client.runs.list.mockImplementation(async () => ({ items: [completedRun()] }));
    client.runs.events.mockImplementation(() =>
      replay([event('1', 'message.delta', { delta: '周报' })]),
    );
    render(<App />);

    await userEvent.click(await screen.findByRole('button', { name: '周报讨论' }));

    // Check after the stream has ended and triggered the refresh, not before
    // the initial saved reply has been replaced (if the fallback is broken).
    await waitFor(() => expect(client.messages.list).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('周报已生成')).toBeTruthy();
    expect(screen.queryByText('周报', { exact: true })).toBeNull();
  });
});

function isBefore(a: Node, b: Node): boolean {
  return (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}
