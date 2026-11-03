import { useEffect, useRef } from 'react';
import { ChevronRight } from 'lucide-react';
import type { AgentEvent, AgentFile, Message, Run } from '@personal-agent/sdk';
import { contextManifest, toolSteps } from '../lib/events';
import { isActive, STATUS_LABELS } from '../lib/labels';
import { groupTurns } from '../lib/turns';
import { Composer } from './Composer';
import { ExecutionDetails } from './ExecutionDetails';
import { MessageList } from './MessageList';
import { Welcome, type Suggestion } from './Welcome';

type ComposerProps = Parameters<typeof Composer>[0];

interface ChatViewProps {
  messages: Message[];
  run: Run | undefined;
  events: AgentEvent[];
  live: string;
  artifacts: AgentFile[];
  composer: Omit<ComposerProps, 'running'>;
  onSuggest: (suggestion: Suggestion) => void;
  onPreviewArtifact: (file: AgentFile) => void;
  onDownloadArtifact: (file: AgentFile) => void;
  onOpenSettings: () => void;
}

export function ChatView(props: ChatViewProps) {
  const { messages, run, events, live } = props;
  const running = isActive(run);
  const steps = toolSteps(events);
  const manifest = contextManifest(events);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messages.length || live || events.length) {
      bottom.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, live, events.length]);

  return (
    <>
      <div className="chat-scroll">
        {messages.length === 0 && !running ? (
          <Welcome onSuggest={props.onSuggest} />
        ) : (
          <MessageList
            turns={groupTurns(messages, props.artifacts, run?.id)}
            latestRunId={run?.id}
            live={running ? live : null}
            process={
              (steps.length > 0 || manifest) && (
                <ExecutionDetails
                  steps={steps}
                  manifest={manifest}
                  open={running}
                  statusLabel={run ? STATUS_LABELS[run.status] : ''}
                />
              )
            }
            outcome={run?.error && <div className="run-error">{run.error}</div>}
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
