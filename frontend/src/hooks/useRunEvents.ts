import { useEffect, useEffectEvent, useState } from 'react';
import type { AgentEvent, Run } from '@personal-agent/sdk';
import { client } from '../api/client';
import { isTerminal } from '../lib/timeline';
import { isActive } from '../lib/labels';

const MAX_RETRIES = 4;
const RETRY_DELAY_MS = 1000;

export interface RunEventHandlers {
  /** Whether the user is still looking at this conversation. */
  isCurrent: (conversationId: string) => boolean;
  onRunStarted: (runId: string) => void;
  /** Reload messages/runs/artifacts after the stream ends; resolves to the latest run. */
  onSettled: (conversationId: string, runId: string) => Promise<Run | undefined>;
  onDisconnected: () => void;
}

interface StreamState {
  key: string | null;
  events: AgentEvent[];
}

/**
 * Subscribe to the latest run's event stream (SSE), resuming with Last-Event-ID
 * after a dropped connection and giving up after a few consecutive failures.
 *
 * The hook owns only the stream (the run's events). Everything else is
 * reported through handlers, so the conversation hook stays the single owner of
 * messages and runs.
 */
export function useRunEvents(
  run: Run | undefined,
  conversationId: string | null,
  handlers: RunEventHandlers,
) {
  const runId = run?.id;
  const key = runId && conversationId ? conversationId + '/' + runId : null;
  const [state, setState] = useState<StreamState>({ key, events: [] });
  // A new run (or conversation) starts from an empty stream. Resetting during
  // render, rather than in the effect, avoids one frame of stale events.
  if (state.key !== key) setState({ key, events: [] });

  // Effect events read the latest props without making them effect dependencies:
  // the subscription must restart only when the run or conversation changes, not
  // when the run object is updated (e.g. status → running).
  const startsFinished = useEffectEvent(() => !isActive(run));
  const isCurrent = useEffectEvent((id: string) => handlers.isCurrent(id));
  const runStarted = useEffectEvent((id: string) => handlers.onRunStarted(id));
  const settle = useEffectEvent((id: string, rid: string) => handlers.onSettled(id, rid));
  const disconnected = useEffectEvent(() => handlers.onDisconnected());

  useEffect(() => {
    if (!runId || !conversationId) return;
    const selected = conversationId;
    const streamKey = selected + '/' + runId;
    const abort = new AbortController();
    const append = (event: AgentEvent) =>
      setState((s) => (s.key === streamKey ? { ...s, events: [...s.events, event] } : s));
    let lastId: string | undefined;
    let retries = 0;
    let finished = startsFinished();

    const listen = async () => {
      while (!abort.signal.aborted) {
        try {
          for await (const event of client.runs.events(runId, lastId, abort.signal)) {
            if (!isCurrent(selected)) return;
            lastId = event.id;
            retries = 0;
            append(event);
            if (event.type === 'run.started') runStarted(runId);
            if (isTerminal(event)) finished = true;
          }
          if (!isCurrent(selected) || abort.signal.aborted) return;
          const latest = await settle(selected, runId);
          if (finished || !isActive(latest)) return;
        } catch {
          if (abort.signal.aborted) return;
          if (++retries > MAX_RETRIES) {
            disconnected();
            return;
          }
        }
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
      }
    };
    void listen();
    return () => abort.abort();
  }, [runId, conversationId]);

  return state.events;
}
