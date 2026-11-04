import { useEffect, useState, type FormEvent } from 'react';
import { Check, Settings as SettingsIcon } from 'lucide-react';
import type { Settings } from '@personal-agent/sdk';
import { client } from '../api/client';
import { errorMessage } from '../lib/labels';

type InstructionMode = 'auto' | 'codex' | 'claude';
type Discovery = Awaited<ReturnType<typeof client.discovery>>;

export function SettingsPanel({
  value,
  onSave,
  onError,
}: {
  value: Settings | null;
  onSave: (s: Settings) => void;
  onError: (e: string) => void;
}) {
  const [url, setUrl] = useState(value?.base_url || 'https://api.openai.com/v1');
  const [model, setModel] = useState(value?.model || '');
  const [timezone, setTimezone] = useState(value?.timezone || 'Asia/Shanghai');
  const [instructionMode, setInstructionMode] = useState<InstructionMode>(
    value?.instruction_mode || 'auto',
  );
  const [recordModelCalls, setRecordModelCalls] = useState(value?.record_model_calls ?? false);
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  useEffect(() => {
    client
      .discovery()
      .then(setDiscovery)
      .catch((e) => onError(errorMessage(e)));
  }, [onError]);
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [clearKey, setClearKey] = useState(false);
  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    try {
      const result = await client.settings.save({
        base_url: url,
        model,
        timezone,
        instruction_mode: instructionMode,
        record_model_calls: recordModelCalls,
        api_key: clearKey ? '' : key || null,
      });
      onSave(result);
      setKey('');
      setClearKey(false);
      setSaved(true);
      setDiscovery(await client.discovery());
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="content-page settings-page">
      <div className="eyebrow">MAKE IT YOURS</div>
      <h1>连接你的模型。</h1>
      <p className="muted">在这里配置，所有客户端共用同一个 Agent 后端。</p>
      <form className="settings-form" onSubmit={save}>
        <label>
          工作空间
          <input readOnly value={value?.workspace_path || ''} />
          <small>规则和项目级技能从此目录加载。通过服务启动配置 AGENT_WORKSPACE 指定。</small>
        </label>
        <label>
          时区
          <input
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            required
            placeholder="Asia/Shanghai"
          />
          <small>每次执行按该时区计算日期和星期。</small>
        </label>
        <label>
          规则文件兼容
          <select
            value={instructionMode}
            onChange={(e) => setInstructionMode(e.target.value as InstructionMode)}
          >
            <option value="auto">自动：优先 AGENTS.md，缺失时使用 CLAUDE.md</option>
            <option value="codex">Codex：AGENTS.override.md / AGENTS.md</option>
            <option value="claude">Claude：CLAUDE.md</option>
          </select>
        </label>
        {discovery && (
          <div className="discovery-info">
            <strong>当前加载的规则</strong>
            {discovery.instructions.length ? (
              discovery.instructions.map((r) => <p key={r.path}>{r.path}</p>)
            ) : (
              <p>未发现规则文件；可在工作空间中创建 AGENTS.md。</p>
            )}
            {discovery.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </div>
        )}
        <label>
          模型服务地址{' '}
          <input
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setSaved(false);
            }}
            required
            type="url"
            placeholder="https://api.example.com/v1"
          />
          <small>填写 API Base URL，需支持流式回复和工具调用。</small>
        </label>
        <label>
          模型名称
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            required
            placeholder="填写服务商提供的模型 ID"
          />
        </label>
        <label>
          API 密钥
          <span className="key-status">{value?.has_api_key ? '已保存密钥' : '尚未配置'}</span>
          <input
            type="password"
            autoComplete="new-password"
            value={key}
            onChange={(e) => {
              setKey(e.target.value);
              setClearKey(false);
            }}
            placeholder={value?.has_api_key ? '留空保留现有密钥' : '输入 API Key'}
          />
          <small>
            密钥仅保存在本机后端，不回传到页面，不写入 Git。请求会将任务材料发送到你配置的模型服务。
          </small>
        </label>
        {value?.has_api_key && (
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={clearKey}
              onChange={(e) => setClearKey(e.target.checked)}
            />
            清除已保存密钥（清除后需重新配置才能使用）
          </label>
        )}
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={recordModelCalls}
            onChange={(e) => setRecordModelCalls(e.target.checked)}
          />
          保存完整模型交互（学习用，默认关闭）
        </label>
        <p className="muted">
          开启后，新执行的请求 JSON、原始响应、回复与工具调用会保存在本机，包含对话和文件正文。
          不保存鉴权 headers，配置密钥会脱敏。关闭只影响后续执行，已有记录仍可查看。
        </p>
        <div className="form-footer">
          <span>
            {saved ? (
              <>
                <Check size={15} />
                配置已保存
              </>
            ) : (
              '更换服务地址时，请重新输入对应密钥。'
            )}
          </span>
          <button className="primary-button" disabled={saving} type="submit">
            {saving ? '保存中…' : '保存配置'}
          </button>
        </div>
      </form>
      <div className="note">
        <SettingsIcon size={16} />
        当前配置为本机单用户使用。首版不包含定时调度、跨重启任务续跑和桌面壳。
      </div>
    </div>
  );
}
