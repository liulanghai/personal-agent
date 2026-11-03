import { useEffect, useState } from 'react';
import { Activity, ChevronRight } from 'lucide-react';
import type { Run } from '@personal-agent/sdk';
import { client } from '../api/client';
import { errorMessage, STATUS_LABELS } from '../lib/labels';

const POLL_INTERVAL_MS = 3000;

interface TaskPanelProps {
  onSelect: (conversationId: string) => void;
  onError: (message: string) => void;
}

export function TaskPanel({ onSelect, onError }: TaskPanelProps) {
  const [runs, setRuns] = useState<Run[]>([]);
  useEffect(() => {
    let closed = false;
    const load = () =>
      client.runs
        .list()
        .then((r) => {
          if (!closed) setRuns(r.items);
        })
        .catch((e) => {
          if (!closed) onError(errorMessage(e));
        });
    void load();
    const timer = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => {
      closed = true;
      clearInterval(timer);
    };
  }, [onError]);

  return (
    <div className="content-page">
      <div className="eyebrow">WORK IN MOTION</div>
      <h1>每一步，都有迹可循。</h1>
      <p className="muted">查看真实执行状态，回到对话继续工作。</p>
      <div className="task-list">
        {runs.length === 0 ? (
          <div className="empty-panel">
            <Activity size={28} />
            <p>还没有执行记录。发起一段对话，开始第一项任务。</p>
          </div>
        ) : (
          runs.map((r) => (
            <button key={r.id} className="task-item" onClick={() => onSelect(r.conversation_id)}>
              <Activity size={20} />
              <div>
                <strong>{r.skill_id || 'Agent 任务'}</strong>
                <small>
                  {new Date(r.created_at).toLocaleString('zh-CN')} · {r.id.slice(0, 12)}
                </small>
              </div>
              <span className={`status ${r.status}`}>{STATUS_LABELS[r.status]}</span>
              <ChevronRight size={16} />
            </button>
          ))
        )}
      </div>
    </div>
  );
}
