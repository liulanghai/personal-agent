/**
 * Pure helpers that turn the run event stream into UI state. Kept free of React
 * so they can be unit tested and reused by future views (S1 approvals, retries).
 */
import type { AgentEvent } from '@personal-agent/sdk';

export const TERMINAL_EVENTS = ['run.completed', 'run.failed', 'run.cancelled'];

export type ToolStepStatus = 'running' | 'succeeded' | 'failed';

export interface ToolStep {
  id: string;
  name: string;
  status: ToolStepStatus;
  arguments: unknown;
  result: unknown;
}

export function isTerminal(event: AgentEvent): boolean {
  return TERMINAL_EVENTS.includes(event.type);
}

/** Pair each `tool_call.started` with its `tool_call.completed`, in start order. */
export function toolSteps(events: AgentEvent[]): ToolStep[] {
  return events
    .filter((e) => e.type === 'tool_call.started')
    .map((started) => {
      const done = events.find(
        (e) =>
          e.type === 'tool_call.completed' && e.data.tool_call_id === started.data.tool_call_id,
      );
      let status: ToolStepStatus = 'running';
      if (done) status = done.data.status === 'failed' ? 'failed' : 'succeeded';
      return {
        id: started.id,
        name: String(started.data.tool_name),
        status,
        arguments: started.data.arguments,
        result: done?.data.result,
      };
    });
}

/** The context manifest of the run these events belong to, if it has been built. */
export function contextManifest(events: AgentEvent[]): Record<string, unknown> | undefined {
  return events.find((e) => e.type === 'context.built')?.data;
}
