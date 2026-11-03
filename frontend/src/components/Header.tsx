import { ChevronRight, Menu } from 'lucide-react';
import type { Page } from './Sidebar';

const PAGE_TITLES: Record<Exclude<Page, 'chat'>, string> = {
  skills: '技能库',
  settings: '设置与模型',
  tasks: '执行记录',
};

interface HeaderProps {
  page: Page;
  conversationTitle: string;
  model: string | undefined;
  onToggleSidebar: () => void;
}

export function Header({ page, conversationTitle, model, onToggleSidebar }: HeaderProps) {
  return (
    <header>
      <div>
        <button className="icon-button mobile-menu" aria-label="展开导航" onClick={onToggleSidebar}>
          <Menu size={19} />
        </button>
        <span className="breadcrumb">个人空间</span>
        <ChevronRight size={13} />
        <strong>{page === 'chat' ? conversationTitle : PAGE_TITLES[page]}</strong>
      </div>
      <span className="mode-badge">
        <span className="dot" />
        {model || '尚未配置模型'}
      </span>
    </header>
  );
}
