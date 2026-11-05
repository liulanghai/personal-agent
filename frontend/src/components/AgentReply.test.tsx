import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { AgentEvent, Message, Run } from '@personal-agent/sdk';
import { AgentReply } from './AgentReply';

const NOW = '2026-11-04T08:00:00Z';

function run(status: Run['status']): Run {
  return {
    id: 'r1',
    conversation_id: 'c1',
    status,
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

const callbacks = { runId: 'r1', onPreviewArtifact: vi.fn(), onDownloadArtifact: vi.fn() };

describe('AgentReply', () => {
  it('keeps the same reply and open step when a live run finishes', async () => {
    const start = [
      event('1', 'message.delta', { delta: '先读文件' }),
      event('2', 'tool_call.started', {
        tool_call_id: 't1',
        tool_name: 'read_file',
        arguments: { path: 'notes.md' },
      }),
    ];
    const { rerender } = render(
      <AgentReply {...callbacks} run={run('running')} events={[]} replies={[]} artifacts={[]} />,
    );
    const reply = screen.getByText('正在处理').closest('.message.assistant');
    expect(screen.getByText('正在思考与执行')).toBeTruthy();

    rerender(
      <AgentReply {...callbacks} run={run('running')} events={start} replies={[]} artifacts={[]} />,
    );
    expect(screen.getByText('先读文件')).toBeTruthy();
    expect(screen.getByText('执行中')).toBeTruthy();
    const summary = screen.getByText('read_file');
    const step = summary.closest('details')!;
    expect(step.open).toBe(false);
    await userEvent.click(summary);
    expect(step.open).toBe(true);

    const finish = [
      ...start,
      event('3', 'tool_call.completed', {
        tool_call_id: 't1',
        status: 'succeeded',
        result: { content: 'file content' },
      }),
      event('4', 'message.delta', { delta: '读完了' }),
      event('5', 'run.completed'),
    ];
    const saved: Message = {
      id: 'm1',
      conversation_id: 'c1',
      run_id: 'r1',
      role: 'assistant',
      content: '先读文件\n\n读完了',
      created_at: NOW,
    };
    rerender(
      <AgentReply
        {...callbacks}
        run={run('completed')}
        events={finish}
        replies={[saved]}
        artifacts={[]}
      />,
    );

    expect(screen.getByText('读完了').closest('.message.assistant')).toBe(reply);
    expect(screen.getByText('read_file').closest('details')).toBe(step);
    expect(step.open).toBe(true);
    expect(screen.getByText('完成')).toBeTruthy();
    expect(step.querySelector('pre')?.textContent).toContain('notes.md');
    expect(step.querySelector('pre')?.textContent).toContain('file content');
    expect(screen.getAllByText('先读文件')).toHaveLength(1);
    expect(screen.getAllByText('读完了')).toHaveLength(1);
    expect(screen.queryByText('正在处理')).toBeNull();
    expect(screen.queryByText('正在思考与执行')).toBeNull();
  });

  it('keeps streamed text before a run failure', () => {
    render(
      <AgentReply
        {...callbacks}
        run={{ ...run('failed'), error: '连接失败' }}
        events={[
          event('1', 'message.delta', { delta: '已经读到的内容' }),
          event('2', 'run.failed', { error: '连接失败' }),
        ]}
        replies={[]}
        artifacts={[]}
      />,
    );

    const text = screen.getByText('已经读到的内容');
    const error = screen.getByText('连接失败');
    expect(text.closest('.message.assistant')).toBe(error.closest('.message.assistant'));
    expect(text.compareDocumentPosition(error) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
  });

  it('shows cancellation after the streamed text', () => {
    render(
      <AgentReply
        {...callbacks}
        run={run('cancelled')}
        events={[event('1', 'message.delta', { delta: '部分回复' }), event('2', 'run.cancelled')]}
        replies={[]}
        artifacts={[]}
      />,
    );

    expect(screen.getByText('部分回复')).toBeTruthy();
    expect(screen.getByText('已取消')).toBeTruthy();
    expect(screen.queryByText('正在处理')).toBeNull();
  });

  it('shows unknown events as expandable steps with their data', async () => {
    render(
      <AgentReply
        {...callbacks}
        run={run('completed')}
        events={[event('1', 'custom.progress', { phase: 'indexing' }), event('2', 'run.completed')]}
        replies={[]}
        artifacts={[]}
      />,
    );

    const title = screen.getByText('custom.progress');
    const step = title.closest('details')!;
    expect(step.open).toBe(false);
    await userEvent.click(title);
    expect(step.open).toBe(true);
    expect(step.querySelector('pre')?.textContent).toContain('indexing');
  });
});
