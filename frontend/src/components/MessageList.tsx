import { Fragment, type ReactNode } from 'react';
import Markdown from 'react-markdown';
import type { AgentFile, Message } from '@personal-agent/sdk';
import type { Turn } from '../lib/turns';
import { ArtifactList } from './ArtifactList';
import { ExecutionDetails } from './ExecutionDetails';

function MessageItem({ message }: { message: Message }) {
  const mine = message.role === 'user';
  const time = new Date(message.created_at).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return (
    <div className={`message ${message.role}`}>
      <div className="message-avatar">{mine ? '我' : '栖'}</div>
      <div className="message-body">
        <div className="message-author">
          {mine ? '你' : '栖'}
          <small>{time}</small>
        </div>
        <Markdown>{message.content}</Markdown>
      </div>
    </div>
  );
}

/** The assistant bubble shown while a run is active: live text or a thinking hint. */
function LiveReply({ text }: { text: string }) {
  return (
    <div className="message assistant">
      <div className="message-avatar">栖</div>
      <div className="message-body">
        <div className="message-author">
          栖 <small>正在处理</small>
        </div>
        {text ? (
          <Markdown>{text}</Markdown>
        ) : (
          <span className="thinking">
            正在思考与执行<span>•••</span>
          </span>
        )}
      </div>
    </div>
  );
}

interface MessageListProps {
  turns: Turn[];
  latestRunId: string | undefined;
  /** Live assistant text of the latest run; `null` when no run is active. */
  live: string | null;
  /** Shown in the latest turn between the prompt and the reply (execution details). */
  process?: ReactNode;
  /** Shown in the latest turn after the reply (run error). */
  outcome?: ReactNode;
  onPreviewArtifact: (file: AgentFile) => void;
  onDownloadArtifact: (file: AgentFile) => void;
}

/** Each turn reads top to bottom: prompt → execution → reply → artifacts. */
export function MessageList(props: MessageListProps) {
  const { turns, latestRunId, live } = props;
  return (
    <div className="message-list">
      {turns.map((turn) => {
        const latest = turn.runId === latestRunId;
        return (
          <Fragment key={turn.runId}>
            {turn.prompts.map((m) => (
              <MessageItem key={m.id} message={m} />
            ))}
            {latest ? (
              props.process
            ) : (
              <ExecutionDetails
                runId={turn.runId}
                steps={undefined}
                manifest={undefined}
                open={false}
                statusLabel="历史执行"
              />
            )}
            {turn.replies.map((m) => (
              <MessageItem key={m.id} message={m} />
            ))}
            {latest && live !== null && <LiveReply text={live} />}
            {latest && props.outcome}
            {turn.artifacts.length > 0 && (
              <ArtifactList
                artifacts={turn.artifacts}
                onPreview={props.onPreviewArtifact}
                onDownload={props.onDownloadArtifact}
              />
            )}
          </Fragment>
        );
      })}
    </div>
  );
}
