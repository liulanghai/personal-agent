import { useEffect, useState } from 'react';
import { Copy, RefreshCw, Radio } from 'lucide-react';
import type { ModelCall } from '@personal-agent/sdk';
import { client } from '../api/client';
import { errorMessage } from '../lib/labels';

const LABELS = {
  running: '接收中',
  completed: '完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '重启中断',
};

function DataSection({ title, text }: { title: string; text: string }) {
  const [feedback, setFeedback] = useState('');
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setFeedback('已复制');
    } catch {
      setFeedback('复制失败，请手动选择文本');
    }
  }
  return (
    <details className="model-data">
      <summary>{title}</summary>
      <div className="model-copy">
        <button type="button" onClick={() => void copy()}>
          <Copy size={13} /> 复制{title}
        </button>
        <span role="status">{feedback}</span>
      </div>
      <pre>{text || '暂无数据'}</pre>
    </details>
  );
}

/** Load only when opened, including historical turns; refresh while receiving. */
export function ModelCalls({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false);
  const [calls, setCalls] = useState<ModelCall[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!open) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      setLoading(true);
      try {
        // Read status first: once terminal, the following query includes the final call.
        const run = await client.runs.get(runId);
        if (disposed) return;
        const result = await client.runs.modelCalls(runId);
        if (disposed) return;
        setCalls(result.items);
        setError('');
        // Continue between HTTP calls while the agent executes tools.
        if (!disposed && (run.status === 'queued' || run.status === 'running')) {
          timer = setTimeout(() => void load(), 2000);
        }
      } catch (e) {
        if (!disposed) setError(errorMessage(e));
      } finally {
        if (!disposed) setLoading(false);
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [open, runId, revision]);
  return (
    <details className="step model-calls" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <Radio size={14} /> 模型调用{' '}
        <span>{open ? `${calls.length} 次 HTTP 调用` : '查看交互记录'}</span>
      </summary>
      {open && (
        <div className="model-call-list">
          <p className="muted">本机学习记录可能包含对话和文件正文，鉴权信息已移除。</p>
          <button type="button" onClick={() => setRevision((v) => v + 1)} disabled={loading}>
            <RefreshCw size={13} /> {loading ? '加载中…' : '刷新记录'}
          </button>
          {error && <p role="alert">{error}</p>}
          {!calls.length && !loading && !error && (
            <p className="muted">
              暂无记录。可在模型设置中开启完整交互记录，开启前的调用无法补录。
            </p>
          )}
          {calls.map((call) => (
            <details className="model-call" key={call.id}>
              <summary>
                <strong>
                  #{call.sequence} · {call.model}
                </strong>
                <span>
                  {LABELS[call.status]} · {call.http_status ?? '无 HTTP 状态'} · {call.duration_ms}{' '}
                  ms
                </span>
              </summary>
              <dl className="model-overview">
                <dt>接口</dt>
                <dd>
                  {call.method} {call.url}
                </dd>
                <dt>开始时间</dt>
                <dd>{new Date(call.started_at).toLocaleString('zh-CN')}</dd>
                <dt>结束时间</dt>
                <dd>
                  {call.finished_at ? new Date(call.finished_at).toLocaleString('zh-CN') : '进行中'}
                </dd>
                <dt>关联</dt>
                <dd>
                  {call.conversation_id} / {call.run_id} / {call.id}
                </dd>
              </dl>
              <DataSection title="请求 JSON" text={JSON.stringify(call.request, null, 2)} />
              <DataSection title="整理响应" text={JSON.stringify(call.response, null, 2)} />
              <DataSection title="原始流式数据" text={call.raw_response} />
              {call.error && <DataSection title="错误" text={call.error} />}
            </details>
          ))}
        </div>
      )}
    </details>
  );
}
