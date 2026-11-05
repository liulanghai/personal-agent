import { Fragment } from 'react';
import Markdown from 'react-markdown';
import type { AgentEvent, AgentFile, Message, Run } from '@personal-agent/sdk';
import type { Turn } from '../lib/turns';
import { AgentReply } from './AgentReply';

function UserMessage({ message }: { message: Message }) {
  const time = new Date(message.created_at).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return (
    <div className="message user">
      <div className="message-avatar">我</div>
      <div className="message-body">
        <div className="message-author">
          你<small>{time}</small>
        </div>
        <Markdown>{message.content}</Markdown>
      </div>
    </div>
  );
}

interface MessageListProps {
  turns: Turn[];
  runs: Run[];
  latestRunId: string | undefined;
  /** Events of the latest run; older runs have none loaded. */
  events: AgentEvent[];
  onPreviewArtifact: (file: AgentFile) => void;
  onDownloadArtifact: (file: AgentFile) => void;
}

/** Each turn is the user's prompt followed by the agent's reply for that run. */
export function MessageList(props: MessageListProps) {
  const runs = new Map(props.runs.map((r) => [r.id, r]));
  return (
    <div className="message-list">
      {props.turns.map((turn) => (
        <Fragment key={turn.runId}>
          {turn.prompts.map((m) => (
            <UserMessage key={m.id} message={m} />
          ))}
          <AgentReply
            runId={turn.runId}
            run={runs.get(turn.runId)}
            replies={turn.replies}
            events={turn.runId === props.latestRunId ? props.events : undefined}
            artifacts={turn.artifacts}
            onPreviewArtifact={props.onPreviewArtifact}
            onDownloadArtifact={props.onDownloadArtifact}
          />
        </Fragment>
      ))}
    </div>
  );
}
