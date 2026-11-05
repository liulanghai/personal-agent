/**
 * Turn a run's event stream into the items of the agent's reply, in the order
 * the loop produced them. Nothing here knows about specific tools or skills:
 * every item comes from an event type, and unknown types are kept as generic
 * items so new loop events show up before the UI learns about them.
 */
import type { AgentEvent } from '@personal-agent/sdk';

export type ToolStatus = 'running' | 'succeeded' | 'failed';
export type EndStatus = 'completed' | 'failed' | 'cancelled';

export type TimelineItem =
  | { kind: 'context'; id: string; manifest: Record<string, unknown> }
  | { kind: 'text'; id: string; text: string }
  | {
      kind: 'tool';
      id: string;
      callId: string;
      name: string;
      status: ToolStatus;
      arguments: unknown;
      result: unknown;
    }
  | { kind: 'end'; id: string; status: EndStatus; error?: string }
  | { kind: 'event'; id: string; type: string; data: Record<string, unknown> };

const END_STATUS: Record<string, EndStatus> = {
  'run.completed': 'completed',
  'run.failed': 'failed',
  'run.cancelled': 'cancelled',
};

/** Lifecycle events with nothing to show: the reply header already says the run is active. */
const SILENT_EVENTS = new Set(['run.started']);

/** Whether this event ends its run (the stream will deliver nothing after it). */
export function isTerminal(event: AgentEvent): boolean {
  return Object.hasOwn(END_STATUS, event.type);
}

export function buildTimeline(events: AgentEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  const tools = new Map<string, Extract<TimelineItem, { kind: 'tool' }>>();

  for (const event of events) {
    const { type, data } = event;
    const last = items[items.length - 1];

    if (type === 'message.delta') {
      // Consecutive deltas form one text segment; any other item ends it.
      const delta = String(data.delta ?? '');
      if (last?.kind === 'text') last.text += delta;
      else items.push({ kind: 'text', id: event.id, text: delta });
    } else if (type === 'context.built') {
      items.push({ kind: 'context', id: event.id, manifest: data });
    } else if (type === 'tool_call.started' || type === 'tool_call.completed') {
      const callId = String(data.tool_call_id);
      let tool = tools.get(callId);
      if (!tool) {
        tool = {
          kind: 'tool',
          id: event.id,
          callId,
          name: String(data.tool_name),
          status: 'running',
          arguments: data.arguments,
          result: undefined,
        };
        tools.set(callId, tool);
        items.push(tool);
      }
      if (type === 'tool_call.completed') {
        tool.status = data.status === 'failed' ? 'failed' : 'succeeded';
        tool.result = data.result;
      }
    } else if (isTerminal(event)) {
      const error = typeof data.error === 'string' ? data.error : undefined;
      items.push({ kind: 'end', id: event.id, status: END_STATUS[type], error });
    } else if (!SILENT_EVENTS.has(type)) {
      items.push({ kind: 'event', id: event.id, type, data });
    }
  }
  return items;
}

/** Whether the stream reached the run's end, i.e. the timeline is the whole reply. */
export function isComplete(items: TimelineItem[]): boolean {
  return items.some((item) => item.kind === 'end');
}
