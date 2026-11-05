import { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import type { AgentFile, Conversation, Settings, Skill } from '@personal-agent/sdk';
import { client } from './api/client';
import { ChatView } from './components/ChatView';
import { Header } from './components/Header';
import { PreviewModal, type Preview } from './components/PreviewModal';
import { SettingsPanel } from './components/SettingsPanel';
import { Sidebar, type Page } from './components/Sidebar';
import { SkillsPanel } from './components/SkillsPanel';
import { TaskPanel } from './components/TaskPanel';
import type { Suggestion } from './components/Welcome';
import { useConversation } from './hooks/useConversation';
import { useRunEvents } from './hooks/useRunEvents';
import { downloadText } from './lib/download';
import { errorMessage, isActive } from './lib/labels';

const MAX_ATTACHMENTS = 10;
const DISCONNECTED = '进度连接中断，任务仍在后台执行。重新选择会话可恢复。';

export function App() {
  const [page, setPage] = useState<Page>('chat');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [skill, setSkill] = useState('');
  const [draft, setDraft] = useState('');
  const [files, setFiles] = useState<AgentFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [sidebar, setSidebar] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);

  const conversation = useConversation(setError);
  const run = conversation.runs[0];
  const events = useRunEvents(run, conversation.conversationId, {
    isCurrent: conversation.isCurrent,
    onRunStarted: conversation.markRunning,
    onSettled: conversation.refreshAfterRun,
    onDisconnected: () => setError(DISCONNECTED),
  });

  const refreshConversations = useCallback(
    () => client.conversations.list().then((r) => setConversations(r.items)),
    [],
  );
  const refreshSkills = () =>
    client.skills
      .list()
      .then((r) => setSkills(r.items))
      .catch((e) => setError(errorMessage(e)));

  useEffect(() => {
    Promise.all([
      refreshConversations(),
      client.skills.list().then((r) => setSkills(r.items)),
      client.settings.get().then(setSettings),
    ]).catch((e) => setError(errorMessage(e)));
  }, [refreshConversations]);

  const { select } = conversation;
  const chooseConversation = useCallback(
    (id: string | null) => {
      select(id);
      setFiles([]);
      setPage('chat');
      setSidebar(false);
      setError('');
    },
    [select],
  );

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'n') {
        event.preventDefault();
        chooseConversation(null);
      }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, [chooseConversation]);

  async function send() {
    if (!draft.trim() || busy || isActive(run)) return;
    setBusy(true);
    setError('');
    try {
      let target = conversation.conversationId;
      if (!target) {
        target = (await client.conversations.create()).id;
        select(target);
      }
      const result = await client.messages.send(target, {
        content: draft,
        skill_id: skill || null,
        file_ids: files.map((f) => f.id),
      });
      const sent = await client.messages.list(target);
      if (conversation.showSent(target, sent.items, result)) {
        setDraft('');
        setFiles([]);
      }
      await refreshConversations();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function upload(list: FileList | null) {
    if (!list) return;
    setBusy(true);
    setError('');
    try {
      for (const file of Array.from(list)) {
        const result = await client.files.upload(file);
        setFiles((old) => [...old, result].slice(0, MAX_ATTACHMENTS));
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
      if (uploadRef.current) uploadRef.current.value = '';
    }
  }

  function cancelRun() {
    if (!run) return;
    client.runs
      .cancel(run.id)
      .then(conversation.replaceLatestRun)
      .catch((e) => setError(errorMessage(e)));
  }

  function previewFile(file: AgentFile) {
    client.files
      .content(file.id)
      .then((content) => setPreview({ title: file.name, content }))
      .catch((e) => setError(errorMessage(e)));
  }

  async function download(file: AgentFile) {
    try {
      downloadText(file.name, await client.files.content(file.id));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  function suggest(suggestion: Suggestion) {
    if (suggestion.skill) setSkill(suggestion.skill);
    setDraft(suggestion.draft);
    if (suggestion.upload) uploadRef.current?.click();
  }

  const title =
    conversations.find((c) => c.id === conversation.conversationId)?.title || '新的开始';

  return (
    <div className="app">
      <Sidebar
        visible={sidebar}
        page={page}
        skillCount={skills.length}
        conversations={conversations}
        currentId={conversation.conversationId}
        onNavigate={setPage}
        onSelect={chooseConversation}
        onClose={() => setSidebar(false)}
      />
      <main>
        <Header
          page={page}
          conversationTitle={title}
          model={settings?.model}
          onToggleSidebar={() => setSidebar(!sidebar)}
        />
        {error && (
          <div className="error" role="alert">
            {error}
            <button onClick={() => setError('')} aria-label="关闭错误">
              <X size={15} />
            </button>
          </div>
        )}
        {page === 'settings' ? (
          settings ? (
            <SettingsPanel value={settings} onSave={setSettings} onError={setError} />
          ) : (
            <p className="muted" role="status">
              正在加载模型设置…
            </p>
          )
        ) : page === 'skills' ? (
          <SkillsPanel
            skills={skills}
            onRefresh={() => void refreshSkills()}
            onShow={(s) =>
              client.skills
                .get(s.id)
                .then((v) => setPreview({ title: s.name, content: v.content }))
                .catch((e) => setError(errorMessage(e)))
            }
            onUse={(s) => {
              setSkill(s.id);
              setPage('chat');
            }}
          />
        ) : page === 'tasks' ? (
          <TaskPanel onSelect={chooseConversation} onError={setError} />
        ) : (
          <ChatView
            messages={conversation.messages}
            runs={conversation.runs}
            events={events}
            artifacts={conversation.artifacts}
            composer={{
              draft,
              files,
              skills,
              skill,
              busy,
              onDraftChange: setDraft,
              onSkillChange: setSkill,
              onRemoveFile: (id) => setFiles((old) => old.filter((f) => f.id !== id)),
              onUpload: () => uploadRef.current?.click(),
              onSend: () => void send(),
              onCancel: cancelRun,
            }}
            onSuggest={suggest}
            onPreviewArtifact={previewFile}
            onDownloadArtifact={(f) => void download(f)}
            onOpenSettings={() => setPage('settings')}
          />
        )}
      </main>
      <input
        type="file"
        ref={uploadRef}
        hidden
        multiple
        accept=".md,.txt,.csv,.json,.log"
        onChange={(e) => void upload(e.target.files)}
      />
      {preview && <PreviewModal preview={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
