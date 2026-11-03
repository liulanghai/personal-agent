import { ChevronRight, FileText, Layers, Sparkles } from 'lucide-react';

export interface Suggestion {
  skill?: string;
  draft: string;
  upload: boolean;
}

const SUGGESTIONS = [
  {
    icon: FileText,
    title: '读懂一份文档',
    hint: '提炼重点，保留依据',
    value: {
      skill: 'document-summary',
      draft: '请总结我上传的文档，保留关键结论并注明来源。',
      upload: true,
    },
  },
  {
    icon: Layers,
    title: '整理本周进展',
    hint: '把零散笔记变成周报',
    value: { skill: 'weekly-report', draft: '请根据我上传的笔记生成本周周报。', upload: true },
  },
  {
    icon: Sparkles,
    title: '认识我的能力',
    hint: '探索工具与工作方式',
    value: { draft: '你有哪些工具和技能？可以怎样帮助我？', upload: false },
  },
];

export function Welcome({ onSuggest }: { onSuggest: (suggestion: Suggestion) => void }) {
  return (
    <div className="welcome">
      <div className="welcome-symbol">
        <Sparkles size={30} strokeWidth={1.3} />
      </div>
      <div className="eyebrow">A LITTLE SPACE FOR BIG IDEAS</div>
      <h1>
        把想法交给我，
        <br />
        <span>一起把事情做好。</span>
      </h1>
      <p>
        从一份笔记、一个问题，或一项具体的工作开始。
        <br />
        我会使用工具与技能，把过程和结果留在这里。
      </p>
      <div className="suggestions">
        {SUGGESTIONS.map(({ icon: Icon, title, hint, value }) => (
          <button key={title} onClick={() => onSuggest(value)}>
            <Icon size={20} />
            <strong>{title}</strong>
            <span>
              {hint} <ChevronRight size={13} />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
