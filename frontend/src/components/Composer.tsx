import { ArrowUp, FileText, Layers, LoaderCircle, Paperclip, Square, X } from 'lucide-react';
import type { AgentFile, Skill } from '@personal-agent/sdk';
import { skillDisplayName } from '../lib/labels';

interface ComposerProps {
  draft: string;
  files: AgentFile[];
  skills: Skill[];
  skill: string;
  busy: boolean;
  running: boolean;
  onDraftChange: (draft: string) => void;
  onSkillChange: (skill: string) => void;
  onRemoveFile: (id: string) => void;
  onUpload: () => void;
  onSend: () => void;
  onCancel: () => void;
}

export function Composer(props: ComposerProps) {
  const { draft, busy, running } = props;
  return (
    <div className="composer">
      {props.files.length > 0 && (
        <div className="attachments">
          {props.files.map((f) => (
            <span key={f.id}>
              <FileText size={14} />
              {f.name}
              <button aria-label={`移除 ${f.name}`} onClick={() => props.onRemoveFile(f.id)}>
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
      )}
      <textarea
        value={draft}
        onChange={(e) => props.onDraftChange(e.target.value)}
        onKeyDown={(e) => {
          // isComposing: Enter confirms an IME candidate, it must not send.
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            props.onSend();
          }
        }}
        placeholder="交代一件事，或一起聊聊你的想法…"
        aria-label="消息"
        rows={2}
      />
      <div className="composer-toolbar">
        <div>
          <button
            className="icon-button"
            title="上传文本文件（最大60KB）"
            aria-label="上传文件"
            disabled={busy || running}
            onClick={props.onUpload}
          >
            <Paperclip size={19} />
          </button>
          <span className="divider" />
          <Layers size={15} />
          <select
            aria-label="选择技能"
            value={props.skill}
            onChange={(e) => props.onSkillChange(e.target.value)}
          >
            <option value="">自动选择技能</option>
            {props.skills.map((s) => (
              <option key={s.id} value={s.id}>
                {skillDisplayName(s.name)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <small>Enter 发送</small>
          {running ? (
            <button className="send-button" aria-label="停止执行" onClick={props.onCancel}>
              <Square size={15} />
            </button>
          ) : (
            <button
              className="send-button"
              aria-label="发送消息"
              onClick={props.onSend}
              disabled={!draft.trim() || busy}
            >
              {busy ? <LoaderCircle className="spin" size={18} /> : <ArrowUp size={20} />}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
