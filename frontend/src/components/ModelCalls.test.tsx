import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ModelCalls } from './ModelCalls';

const client = vi.hoisted(() => ({ runs: { modelCalls: vi.fn(), get: vi.fn() } }));
vi.mock('../api/client', () => ({ client }));

beforeEach(() => {
  vi.clearAllMocks();
  client.runs.get.mockResolvedValue({ status: 'completed' });
});

it('loads a historical run on demand, expands details and copies raw data', async () => {
  const user = userEvent.setup();
  const raw = 'data: {"choices":[]}\n\ndata: [DONE]\n\n';
  client.runs.modelCalls.mockResolvedValue({
    items: [
      {
        id: 'http1',
        run_id: 'old-run',
        conversation_id: 'conv',
        sequence: 1,
        model: 'learning-model',
        method: 'POST',
        url: 'https://example.com/v1/chat/completions',
        started_at: '2026-11-04T00:00:00Z',
        finished_at: '2026-11-04T00:00:01Z',
        duration_ms: 1000,
        http_status: 200,
        status: 'completed',
        request: { messages: [{ role: 'user', content: '文件正文' }], tools: [] },
        response: { content: '完成', usage: { total_tokens: 12 } },
        raw_response: raw,
        error: null,
      },
    ],
  });
  render(<ModelCalls runId="old-run" />);
  expect(client.runs.modelCalls).not.toHaveBeenCalled();
  await user.click(screen.getByText('模型调用'));
  const call = await screen.findByText('#1 · learning-model');
  expect(client.runs.modelCalls).toHaveBeenCalledWith('old-run');
  await user.click(call);
  await user.click(screen.getByText('请求 JSON'));
  expect(screen.getByText(/"content": "文件正文"/)).toBeTruthy();
  await user.click(screen.getByText('原始流式数据'));
  const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
  await user.click(screen.getByRole('button', { name: '复制原始流式数据' }));
  expect(copy).toHaveBeenCalledWith(raw);
  expect(await screen.findByText('已复制')).toBeTruthy();
});

it('reads records after checking run status so a final HTTP call cannot be missed', async () => {
  const user = userEvent.setup();
  client.runs.modelCalls.mockResolvedValue({ items: [] });
  render(<ModelCalls runId="r" />);
  await user.click(screen.getByText('模型调用'));
  await screen.findByText(/开启前的调用无法补录/);
  expect(client.runs.get.mock.invocationCallOrder[0]).toBeLessThan(
    client.runs.modelCalls.mock.invocationCallOrder[0],
  );
});

it('explains absent records and allows retry after a failed query', async () => {
  const user = userEvent.setup();
  client.runs.modelCalls.mockRejectedValueOnce(new Error('读取失败'));
  render(<ModelCalls runId="r" />);
  await user.click(screen.getByText('模型调用'));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '读取失败');
  client.runs.modelCalls.mockResolvedValue({ items: [] });
  await user.click(screen.getByRole('button', { name: '刷新记录' }));
  expect(await screen.findByText(/开启前的调用无法补录/)).toBeTruthy();
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
});
