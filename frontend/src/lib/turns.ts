/**
 * Group a conversation into turns: one turn per run, holding the user prompt,
 * the assistant reply and the artifacts that run produced. The chat view renders
 * a turn as the prompt followed by the agent's reply (its steps, text and
 * artifacts), so results stay next to the request that caused them.
 */
import type { AgentFile, Message } from '@personal-agent/sdk';

export interface Turn {
  runId: string;
  prompts: Message[];
  replies: Message[];
  artifacts: AgentFile[];
}

export function groupTurns(
  messages: Message[],
  artifacts: AgentFile[],
  latestRunId?: string,
): Turn[] {
  const turns: Turn[] = [];
  const byRun = new Map<string, Turn>();
  const turnFor = (runId: string) => {
    let turn = byRun.get(runId);
    if (!turn) {
      turn = { runId, prompts: [], replies: [], artifacts: [] };
      byRun.set(runId, turn);
      turns.push(turn);
    }
    return turn;
  };

  // Messages arrive in insertion order, so turns follow conversation order.
  for (const message of messages) {
    const turn = turnFor(message.run_id);
    if (message.role === 'user') turn.prompts.push(message);
    else turn.replies.push(message);
  }
  // The latest run may not have its messages loaded yet (just sent); it still
  // needs a turn to show progress in.
  if (latestRunId) turnFor(latestRunId);
  // Artifacts are listed per run; one without a loaded turn still gets shown.
  for (const artifact of artifacts) {
    if (artifact.run_id) turnFor(artifact.run_id).artifacts.push(artifact);
  }
  return turns;
}
