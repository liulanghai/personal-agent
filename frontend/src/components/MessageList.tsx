import type { ReactNode } from 'react';
import Markdown from 'react-markdown';
import type { Message } from '@personal-agent/sdk';

function MessageItem({ message }: { message: Message }) {
  const mine = message.role === 'user';
  const time = new Date(message.created_at).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return (
    <div className={`message ${message.role}`}>
      <div className="message-avatar">{mine ? '我' : '栖'}</div>
      <div className="message-body">
        <div className="message-author">
          {mine ? '你' : '栖'}
          <small>{time}</small>
        </div>
        <Markdown>{message.content}</Markdown>
      </div>
    </div>
  );
}

/** The assistant bubble shown while a run is active: live text or a thinking hint. */
function LiveReply({ text }: { text: string }) {
  return (
    <div className="message assistant">
      <div className="message-avatar">栖</div>
      <div className="message-body">
        <div className="message-author">
          栖 <small>正在处理</small>
        </div>
        {text ? (
          <Markdown>{text}</Markdown>
        ) : (
          <span className="thinking">
            正在思考与执行<span>•••</span>
          </span>
        )}
      </div>
    </div>
  );
}

interface MessageListProps {
  messages: Message[];
  /** Live assistant text; `null` when no run is active. */
  live: string | null;
  /** Rendered after the messages and before the live reply (execution details). */
  beforeLive?: ReactNode;
  /** Rendered after the live reply (context button, run error, artifacts). */
  afterLive?: ReactNode;
}

export function MessageList({ messages, live, beforeLive, afterLive }: MessageListProps) {
  return (
    <div className="message-list">
      {messages.map((m) => (
        <MessageItem key={m.id} message={m} />
      ))}
      {beforeLive}
      {live !== null && <LiveReply text={live} />}
      {afterLive}
    </div>
  );
}
