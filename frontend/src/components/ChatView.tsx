import { useEffect, useRef } from 'react';
import { ChevronRight } from 'lucide-react';
import type { AgentEvent, AgentFile, Message, Run } from '@personal-agent/sdk';
import { contextManifest, toolSteps } from '../lib/events';
import { isActive, STATUS_LABELS } from '../lib/labels';
import { ArtifactList } from './ArtifactList';
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
  onShowContext: (manifest: Record<string, unknown>) => void;
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
            messages={messages}
            live={running ? live : null}
            beforeLive={
              steps.length > 0 && (
                <ExecutionDetails
                  steps={steps}
                  open={running}
                  statusLabel={run ? STATUS_LABELS[run.status] : ''}
                />
              )
            }
            afterLive={
              <>
                {manifest && (
                  <button className="context-button" onClick={() => props.onShowContext(manifest)}>
                    查看本次上下文与环境信息
                  </button>
                )}
                {run?.error && <div className="run-error">{run.error}</div>}
                {props.artifacts.length > 0 && (
                  <ArtifactList
                    artifacts={props.artifacts}
                    onPreview={props.onPreviewArtifact}
                    onDownload={props.onDownloadArtifact}
                  />
                )}
              </>
            }
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
