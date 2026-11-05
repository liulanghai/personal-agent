import { useEffect, useRef } from 'react';
import { ChevronRight } from 'lucide-react';
import type { AgentEvent, AgentFile, Message, Run } from '@personal-agent/sdk';
import { isActive } from '../lib/labels';
import { groupTurns } from '../lib/turns';
import { Composer } from './Composer';
import { MessageList } from './MessageList';
import { Welcome, type Suggestion } from './Welcome';

type ComposerProps = Parameters<typeof Composer>[0];

interface ChatViewProps {
  messages: Message[];
  /** Runs of the conversation, newest first. */
  runs: Run[];
  /** Events of the latest run. */
  events: AgentEvent[];
  artifacts: AgentFile[];
  composer: Omit<ComposerProps, 'running'>;
  onSuggest: (suggestion: Suggestion) => void;
  onPreviewArtifact: (file: AgentFile) => void;
  onDownloadArtifact: (file: AgentFile) => void;
  onOpenSettings: () => void;
}

export function ChatView(props: ChatViewProps) {
  const { messages, runs, events } = props;
  const run = runs[0];
  const running = isActive(run);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messages.length || events.length) {
      bottom.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, events]);

  return (
    <>
      <div className="chat-scroll">
        {messages.length === 0 && !running ? (
          <Welcome onSuggest={props.onSuggest} />
        ) : (
          <MessageList
            turns={groupTurns(messages, props.artifacts, run?.id)}
            runs={runs}
            latestRunId={run?.id}
            events={events}
            onPreviewArtifact={props.onPreviewArtifact}
            onDownloadArtifact={props.onDownloadArtifact}
          />
        )}
        <div ref={bottom} />
      </div>
      <div className="composer-wrap">
        <Composer {...props.composer} running={running} />
        <p className="composer-footnote">
          模型可能出错，请核实重要信息。{' '}
          <button onClick={props.onOpenSettings}>
            模型设置 <ChevronRight size={11} />
          </button>
        </p>
      </div>
    </>
  );
}
