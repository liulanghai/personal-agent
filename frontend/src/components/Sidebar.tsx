import {
  Activity,
  Layers,
  MessageSquare,
  PanelLeftClose,
  Plus,
  Settings as SettingsIcon,
} from 'lucide-react';
import type { Conversation } from '@personal-agent/sdk';

export type Page = 'chat' | 'tasks' | 'skills' | 'settings';

interface SidebarProps {
  visible: boolean;
  page: Page;
  skillCount: number;
  conversations: Conversation[];
  currentId: string | null;
  onNavigate: (page: Page) => void;
  onSelect: (id: string | null) => void;
  onClose: () => void;
}

export function Sidebar(props: SidebarProps) {
  const { page, onNavigate } = props;
  const navClass = (target: Page) => (page === target ? 'selected' : '');
  return (
    <aside className={`sidebar ${props.visible ? 'visible' : ''}`}>
      <div className="brand">
        <div className="brand-mark">栖</div>
        <span>
          栖 <small>PERSONAL AGENT</small>
        </span>
        <button className="icon-button collapse" onClick={props.onClose} aria-label="收起导航">
          <PanelLeftClose size={17} />
        </button>
      </div>
      <button className="new-chat" onClick={() => props.onSelect(null)}>
        <Plus size={17} />
        开启新对话<span>⌘ N</span>
      </button>
      <nav>
        <button className={navClass('chat')} onClick={() => onNavigate('chat')}>
          <MessageSquare size={17} />
          对话
        </button>
        <button className={navClass('tasks')} onClick={() => onNavigate('tasks')}>
          <Activity size={17} />
          执行记录
        </button>
        <button className={navClass('skills')} onClick={() => onNavigate('skills')}>
          <Layers size={17} />
          技能库 <span className="count">{props.skillCount}</span>
        </button>
      </nav>
      <div className="section-label">最近对话</div>
      <div className="conversation-list">
        {props.conversations.length === 0 ? (
          <p className="empty-history">你的想法，从这里开始。</p>
        ) : (
          props.conversations.map((c) => (
            <button
              key={c.id}
              className={c.id === props.currentId ? 'current' : ''}
              onClick={() => props.onSelect(c.id)}
            >
              <MessageSquare size={14} />
              <span>{c.title}</span>
            </button>
          ))
        )}
      </div>
      <div className="sidebar-bottom">
        <div className="local-status">
          <span className="dot" />
          本地工作空间<span>v0.1</span>
        </div>
        <button className={navClass('settings')} onClick={() => onNavigate('settings')}>
          <SettingsIcon size={17} />
          设置与模型
        </button>
        <div className="profile">
          <div className="avatar">我</div>
          <div>
            个人空间<small>Local · Private</small>
          </div>
          <span className="profile-tag">本地</span>
        </div>
      </div>
    </aside>
  );
}
