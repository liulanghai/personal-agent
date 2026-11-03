import { AgentClient } from '@personal-agent/sdk';

/** The single SDK client for the app. Tests replace this module with `vi.mock`. */
export const client = new AgentClient(
  '/api/v1',
  sessionStorage.getItem('agent_token') || undefined,
);
