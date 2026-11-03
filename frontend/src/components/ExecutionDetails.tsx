import { Activity, Check, LoaderCircle } from 'lucide-react';
import type { ToolStep } from '../lib/events';

const STEP_LABELS = { running: '执行中', succeeded: '完成', failed: '失败' } as const;

interface ExecutionDetailsProps {
  steps: ToolStep[];
  open: boolean;
  statusLabel: string;
}

export function ExecutionDetails({ steps, open, statusLabel }: ExecutionDetailsProps) {
  return (
    <details className="execution" open={open}>
      <summary>
        <Activity size={15} />
        执行过程 · {steps.length} 次工具调用
        <span>{statusLabel}</span>
      </summary>
      {steps.map((step) => (
        <details key={step.id} className="tool-row">
          <summary>
            {step.status === 'running' ? (
              <LoaderCircle className="spin" size={14} />
            ) : (
              <Check size={14} />
            )}
            <code>{step.name}</code>
            <span>{STEP_LABELS[step.status]}</span>
          </summary>
          <pre>{JSON.stringify({ arguments: step.arguments, result: step.result }, null, 2)}</pre>
        </details>
      ))}
    </details>
  );
}
