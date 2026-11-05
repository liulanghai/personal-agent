import type { ReactNode } from 'react';
import { Check, CircleDot, LoaderCircle, ScrollText, X } from 'lucide-react';
import Markdown from 'react-markdown';
import type { AgentFile, AgentEvent, Message, Run } from '@personal-agent/sdk';
import { isActive } from '../lib/labels';
import { buildTimeline, isComplete, type TimelineItem } from '../lib/timeline';
import { ArtifactList } from './ArtifactList';
import { ModelCalls } from './ModelCalls';

const TOOL_LABELS = { running: '执行中', succeeded: '完成', failed: '失败' } as const;

function json(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

interface StepProps {
  icon: ReactNode;
  title: ReactNode;
  note?: string;
  detail: string;
}

/** One collapsible step line: a tool call, the context build or an unknown event. */
function Step({ icon, title, note, detail }: StepProps) {
  return (
    <details className="step">
      <summary>
        {icon}
        {title}
        {note && <span>{note}</span>}
      </summary>
      <pre>{detail}</pre>
    </details>
  );
}

function TimelineEntry({ item }: { item: TimelineItem }) {
  switch (item.kind) {
    case 'text':
      return <Markdown>{item.text}</Markdown>;
    case 'context':
      return (
        <Step
          icon={<ScrollText size={14} />}
          title="构建上下文"
          note="规则、Skill 与环境"
          detail={json(item.manifest)}
        />
      );
    case 'tool': {
      let icon = <Check size={14} />;
      if (item.status === 'running') icon = <LoaderCircle className="spin" size={14} />;
      if (item.status === 'failed') icon = <X size={14} />;
      return (
        <Step
          icon={icon}
          title={<code>{item.name}</code>}
          note={TOOL_LABELS[item.status]}
          detail={json({ arguments: item.arguments, result: item.result })}
        />
      );
    }
    case 'end':
      if (item.status === 'failed') return <div className="run-error">{item.error}</div>;
      if (item.status === 'cancelled') return <p className="run-note">已取消</p>;
      return null;
    case 'event':
      return (
        <Step
          icon={<CircleDot size={14} />}
          title={<code>{item.type}</code>}
          detail={json(item.data)}
        />
      );
  }
}

function Thinking() {
  return (
    <span className="thinking">
      正在思考与执行<span>•••</span>
    </span>
  );
}

interface AgentReplyProps {
  /** Available from the turn even if this run is outside the loaded run list. */
  runId: string;
  run: Run | undefined;
  /** Saved assistant messages of this run (the final text, no steps). */
  replies: Message[];
  /** The run's event stream, if it is loaded (latest run only). */
  events: AgentEvent[] | undefined;
  artifacts: AgentFile[];
  onPreviewArtifact: (file: AgentFile) => void;
  onDownloadArtifact: (file: AgentFile) => void;
}

/**
 * The agent's side of one turn. With events it replays exactly what the loop
 * produced, in order (text, tool calls, context, the end of the run); without
 * them it falls back to the saved reply text and the run's error.
 */
export function AgentReply(props: AgentReplyProps) {
  const { run, replies } = props;
  // Annotated so TypeScript does not narrow `run` away when this is false.
  const running: boolean = isActive(run);
  const timeline = buildTimeline(props.events ?? []);
  // A finished run whose stream did not reach the end (not loaded yet, or the
  // connection dropped) would show a partial reply; use the saved one instead.
  const useTimeline = running || isComplete(timeline);

  const last = timeline[timeline.length - 1];
  const busyStep = last?.kind === 'text' || (last?.kind === 'tool' && last.status === 'running');
  const time = replies[0]
    ? new Date(replies[0].created_at).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '';

  return (
    <div className="message assistant">
      <div className="message-avatar">栖</div>
      <div className="message-body">
        <div className="message-author">
          栖 <small>{running ? '正在处理' : time}</small>
        </div>
        {useTimeline ? (
          <>
            {timeline.map((item) => (
              <TimelineEntry key={item.id} item={item} />
            ))}
            {running && !busyStep && <Thinking />}
          </>
        ) : (
          <>
            {replies.map((m) => (
              <Markdown key={m.id}>{m.content}</Markdown>
            ))}
            {run?.status === 'failed' && run.error && <div className="run-error">{run.error}</div>}
          </>
        )}
        <ModelCalls key={props.runId} runId={props.runId} />
        {props.artifacts.length > 0 && (
          <ArtifactList
            artifacts={props.artifacts}
            onPreview={props.onPreviewArtifact}
            onDownload={props.onDownloadArtifact}
          />
        )}
      </div>
    </div>
  );
}
