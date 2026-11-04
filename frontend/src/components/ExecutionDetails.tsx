import { Activity, Check, LoaderCircle, ScrollText } from 'lucide-react';
import type { ToolStep } from '../lib/events';

import { ModelCalls } from './ModelCalls';

const STEP_LABELS = { running: '执行中', succeeded: '完成', failed: '失败' } as const;

interface ExecutionDetailsProps {
  runId: string;
  steps: ToolStep[] | undefined;
  /** The run's context manifest; shown as the first step once it has been built. */
  manifest: Record<string, unknown> | undefined;
  open: boolean;
  statusLabel: string;
}

export function ExecutionDetails({
  runId,
  steps,
  manifest,
  open,
  statusLabel,
}: ExecutionDetailsProps) {
  return (
    <details className="execution" open={open}>
      <summary>
        <Activity size={15} />
        执行过程{steps && ` · ${steps.length} 次工具调用`}
        <span>{statusLabel}</span>
      </summary>
      {manifest && (
        <details className="tool-row">
          <summary>
            <ScrollText size={14} />
            构建上下文
            <span>规则、Skill 与环境</span>
          </summary>
          <pre>{JSON.stringify(manifest, null, 2)}</pre>
        </details>
      )}
      <ModelCalls key={runId} runId={runId} />
      {steps?.map((step) => (
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
