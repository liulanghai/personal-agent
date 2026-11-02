import type { components } from './schema';
export type SettingsInput = components['schemas']['SettingsInput'];
export type MessageInput = components['schemas']['MessageInput'];
export type Conversation = components['schemas']['Conversation'];
export type Message = components['schemas']['Message'];
export type Run = components['schemas']['Run'];
export type Skill = components['schemas']['Skill'];
export type AgentFile = components['schemas']['AgentFile'];
export type Settings = components['schemas']['Settings'];
export type AgentEvent = {id: string; sequence: number; run_id: string; type: string; data: Record<string, unknown>; created_at: string};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** Fetch-based SDK works in browsers and desktop webviews, including bearer-authenticated SSE. */
export class AgentClient {
  constructor(public baseUrl = '/api/v1', private token?: string) {}
  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (this.token) headers.set('Authorization', `Bearer ${this.token}`);
    if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    const response = await fetch(this.baseUrl + path, {...init, headers});
    if (!response.ok) {
      const value = await response.json().catch(() => ({}));
      throw new ApiError(response.status, value.error?.message || JSON.stringify(value.detail) || response.statusText);
    }
    return response.json();
  }
  conversations = {
    list: () => this.request<{items: Conversation[]}>('/conversations'),
    create: (title = '新对话') => this.request<Conversation>('/conversations', {method:'POST',body:JSON.stringify({title})})
  };
  messages = {
    list: (cid: string) => this.request<{items: Message[]}>(`/conversations/${cid}/messages`),
    send: (cid: string, input: MessageInput, key = crypto.randomUUID()) => this.request<Run>(`/conversations/${cid}/messages`, {method:'POST', headers:{'Idempotency-Key':key},body:JSON.stringify(input)})
  };
  runs = {
    list: (cid?: string) => this.request<{items: Run[]}>(`/runs${cid ? '?conversation_id='+encodeURIComponent(cid) : ''}`),
    get: (id: string) => this.request<Run>(`/runs/${id}`),
    cancel: (id: string) => this.request<Run>(`/runs/${id}/cancel`, {method:'POST'}),
    events: (id: string, cursor?: string, signal?: AbortSignal) => this.events(id, cursor, signal)
  };
  skills = {
    list: () => this.request<{items: Skill[]}>('/skills'),
    get: (id: string) => this.request<{id: string; content: string}>(`/skills/${id}`)
  };
  settings = {
    get: () => this.request<Settings>('/settings'),
    save: (value: SettingsInput) => this.request<Settings>('/settings', {method:'PUT',body:JSON.stringify(value)})
  };
  files = {
    upload: (file: File) => { const data = new FormData(); data.append('file',file); return this.request<AgentFile>('/files',{method:'POST',body:data}); },
    artifacts: (rid?: string) => this.request<{items: AgentFile[]}>(`/artifacts${rid ? '?run_id='+encodeURIComponent(rid) : ''}`),
    content: async (id: string) => {
      const response = await fetch(`${this.baseUrl}/files/${id}/content`, {headers:this.token ? {Authorization:`Bearer ${this.token}`} : {}});
      if (!response.ok) throw new ApiError(response.status, '文件读取失败');
      return response.text();
    }
  };
  private async *events(id: string, cursor?: string, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
    const headers: Record<string,string> = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    if (cursor) headers['Last-Event-ID'] = cursor;
    const response = await fetch(`${this.baseUrl}/runs/${id}/events`, {headers, signal});
    if (!response.ok || !response.body) throw new ApiError(response.status, '事件连接失败');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (true) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value, {stream:!done}).replace(/\r\n/g,'\n');
        let end: number;
        while ((end = buffer.indexOf('\n\n')) >= 0) {
          const frame = buffer.slice(0,end); buffer = buffer.slice(end+2);
          const data = frame.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
          if (data) yield JSON.parse(data) as AgentEvent;
        }
        if (done) break;
      }
    } finally { await reader.cancel().catch(()=>{}); reader.releaseLock(); }
  }
}
