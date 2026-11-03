import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentFile, Message, Run } from '@personal-agent/sdk';
import { client } from '../api/client';
import { errorMessage } from '../lib/labels';

/**
 * The selected conversation and the data shown for it: messages, runs (newest
 * first) and artifacts. All selection changes go through `select`, which keeps
 * `isCurrent` in sync so late responses for a previous conversation are dropped.
 */
export function useConversation(onError: (message: string) => void) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [artifacts, setArtifacts] = useState<AgentFile[]>([]);
  const currentId = useRef<string | null>(null);

  const isCurrent = useCallback((id: string) => currentId.current === id, []);

  const select = useCallback((id: string | null) => {
    currentId.current = id;
    setConversationId(id);
    setMessages([]);
    setRuns([]);
    setArtifacts([]);
  }, []);

  useEffect(() => {
    if (!conversationId) return;
    const selected = conversationId;
    Promise.all([client.messages.list(selected), client.runs.list(selected)])
      .then(async ([m, r]) => {
        if (!isCurrent(selected)) return;
        setMessages(m.items);
        setRuns(r.items);
        const all = await Promise.all(r.items.map((run) => client.files.artifacts(run.id)));
        if (isCurrent(selected)) setArtifacts(all.flatMap((a) => a.items));
      })
      .catch((e) => onError(errorMessage(e)));
  }, [conversationId, isCurrent, onError]);

  /** Show a just-sent message and its run; returns false if the user moved on. */
  const showSent = useCallback(
    (id: string, sent: Message[], run: Run) => {
      if (!isCurrent(id)) return false;
      setMessages(sent);
      setRuns([run]);
      return true;
    },
    [isCurrent],
  );

  const markRunning = useCallback((runId: string) => {
    setRuns((old) => old.map((r) => (r.id === runId ? { ...r, status: 'running' } : r)));
  }, []);

  const replaceLatestRun = useCallback((run: Run) => {
    setRuns((old) => [run, ...old.slice(1)]);
  }, []);

  /** Reload after a run's event stream ends; resolves to the latest run. */
  const refreshAfterRun = useCallback(async (id: string, runId: string) => {
    const [m, r, a] = await Promise.all([
      client.messages.list(id),
      client.runs.list(id),
      client.files.artifacts(runId),
    ]);
    setMessages(m.items);
    setRuns(r.items);
    setArtifacts((old) => [...old.filter((f) => f.run_id !== runId), ...a.items]);
    return r.items[0];
  }, []);

  return {
    conversationId,
    messages,
    runs,
    artifacts,
    isCurrent,
    select,
    showSent,
    markRunning,
    replaceLatestRun,
    refreshAfterRun,
  };
}
