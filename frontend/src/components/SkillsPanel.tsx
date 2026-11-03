import { ChevronRight, ExternalLink, Layers, Sparkles } from 'lucide-react';
import type { Skill } from '@personal-agent/sdk';
import { skillDisplayName } from '../lib/labels';

interface SkillsPanelProps {
  skills: Skill[];
  onRefresh: () => void;
  onShow: (skill: Skill) => void;
  onUse: (skill: Skill) => void;
}

export function SkillsPanel({ skills, onRefresh, onShow, onUse }: SkillsPanelProps) {
  return (
    <div className="content-page">
      <div className="eyebrow">YOUR TOOLKIT</div>
      <button className="primary-button" style={{ float: 'right' }} onClick={onRefresh}>
        刷新技能
      </button>
      <h1>把方法，变成能力。</h1>
      <p className="muted">Skill 为 Agent 提供可复用的工作流程，执行仍由工具完成。</p>
      <div className="skill-grid">
        {skills.map((s) => (
          <article className="skill-card" key={s.id}>
            <div className="skill-icon">
              <Layers size={22} />
            </div>
            <span className="tag">
              {s.scope} · {s.source}
            </span>
            <h3>{skillDisplayName(s.name)}</h3>
            <p>{s.description}</p>
            <small className="skill-source">{s.path}</small>
            {s.unsupported_fields.length > 0 && (
              <small className="skill-source">
                未启用的扩展字段：{s.unsupported_fields.join(', ')}
              </small>
            )}
            <div className="skill-actions">
              <button onClick={() => onShow(s)}>
                查看说明 <ExternalLink size={13} />
              </button>
              <button onClick={() => onUse(s)}>
                在对话中使用 <ChevronRight size={14} />
              </button>
            </div>
          </article>
        ))}
      </div>
      <div className="note">
        <Sparkles size={16} />
        自动发现用户与工作空间中的 .agents/skills、.claude/skills，兼容
        ~/.codex/skills；正文按需加载。
      </div>
    </div>
  );
}
