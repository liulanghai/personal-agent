import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Markdown from 'react-markdown';
import { ArrowUp, Plus, MessageSquare, Layers, Settings as SettingsIcon, Sparkles, Paperclip, X, FileText, Download, Check, Square, ChevronRight, Activity, PanelLeftClose, Menu, ExternalLink, LoaderCircle } from 'lucide-react';
import { AgentClient, type Conversation, type Message, type Run, type Skill, type AgentFile, type AgentEvent, type Settings } from '@personal-agent/sdk';
import './style.css';

const client = new AgentClient('/api/v1', sessionStorage.getItem('agent_token') || undefined);
const labels: Record<string,string> = {queued:'排队中',running:'进行中',completed:'已完成',failed:'失败',cancelled:'已取消'};
const active = (r?: Run|null) => r && ['queued','running'].includes(r.status);

function App() {
  const [page,setPage] = useState('chat');
  const [conversations,setConversations] = useState<Conversation[]>([]);
  const [cid,setCid] = useState<string|null>(null);
  const [messages,setMessages] = useState<Message[]>([]);
  const [runs,setRuns] = useState<Run[]>([]);
  const [skills,setSkills] = useState<Skill[]>([]);
  const [settings,setSettings] = useState<Settings|null>(null);
  const [skill,setSkill] = useState('');
  const [draft,setDraft] = useState('');
  const [files,setFiles] = useState<AgentFile[]>([]);
  const [artifacts,setArtifacts] = useState<AgentFile[]>([]);
  const [events,setEvents] = useState<AgentEvent[]>([]);
  const [live,setLive] = useState('');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [preview,setPreview] = useState<{title:string;content:string}|null>(null);
  const [sidebar,setSidebar] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const currentCid = useRef(cid); currentCid.current = cid;
  const run = runs[0];

  const refreshConversations = () => client.conversations.list().then(r=>setConversations(r.items));
  useEffect(()=>{
    Promise.all([refreshConversations(),client.skills.list().then(r=>setSkills(r.items)),client.settings.get().then(setSettings)]).catch(e=>setError(e.message));
  },[]);
  useEffect(()=>{
    const shortcut = (event:KeyboardEvent) => {if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='n'){event.preventDefault();chooseConversation(null);}};
    window.addEventListener('keydown',shortcut);
    return ()=>window.removeEventListener('keydown',shortcut);
  },[]);
  useEffect(()=>{
    if (!cid) {setMessages([]);setRuns([]);setArtifacts([]);return;}
    const selected = cid;
    Promise.all([client.messages.list(cid),client.runs.list(cid)]).then(async ([m,r])=>{
      if (currentCid.current !== selected) return;
      setMessages(m.items);setRuns(r.items);
      const all = await Promise.all(r.items.map(run=>client.files.artifacts(run.id)));
      if (currentCid.current === selected) setArtifacts(all.flatMap(a=>a.items));
    }).catch(e=>setError(e.message));
  },[cid]);
  useEffect(()=>{if(messages.length||live||events.length)bottom.current?.scrollIntoView({behavior:'smooth'});},[messages,live,events.length]);
  useEffect(()=>{
    if (!run?.id || !cid) return;
    const abort = new AbortController();
    const selected = cid;
    setEvents([]);setLive('');
    let lastId: string|undefined;
    let retries = 0;
    let text = '';
    let finished = !active(run);
    const listen = async () => {
      while (!abort.signal.aborted) {
        try {
          for await (const event of client.runs.events(run.id,lastId,abort.signal)) {
            if (currentCid.current !== selected) return;
            lastId = event.id; retries = 0;
            setEvents(old=>[...old,event]);
            if(event.type==='run.started')setRuns(old=>old.map(r=>r.id===run.id?{...r,status:'running'}:r));
            if (event.type === 'message.delta') {text += String(event.data.delta); if (!finished) setLive(text);}
            if (event.type.startsWith('run.') && ['run.completed','run.failed','run.cancelled'].includes(event.type)) finished = true;
          }
          if (currentCid.current !== selected || abort.signal.aborted) return;
          const [m,r,a] = await Promise.all([client.messages.list(selected),client.runs.list(selected),client.files.artifacts(run.id)]);
          setMessages(m.items);setRuns(r.items);setLive('');
          setArtifacts(old=>[...old.filter(f=>f.run_id!==run.id),...a.items]);
          if (finished || !active(r.items[0])) return;
        } catch (e) {
          if (abort.signal.aborted) return;
          if (++retries > 4) {setError('进度连接中断，任务仍在后台执行。重新选择会话可恢复。');return;}
        }
        await new Promise(resolve=>setTimeout(resolve,1000));
      }
    };
    void listen();
    return ()=>abort.abort();
  },[run?.id,cid]);

  function chooseConversation(id: string|null) {
    setCid(id);setMessages([]);setRuns([]);setEvents([]);setLive('');setFiles([]);setPage('chat');setSidebar(false);setError('');
  }
  async function send() {
    if (!draft.trim() || busy || active(run)) return;
    setBusy(true);setError('');
    try {
      let target = cid;
      if (!target) {
        const conversation = await client.conversations.create();
        target = conversation.id; currentCid.current = target;setCid(target);
      }
      const result = await client.messages.send(target,{content:draft,skill_id:skill||null,file_ids:files.map(f=>f.id)});
      const m = await client.messages.list(target);
      if (currentCid.current === target) {setMessages(m.items);setRuns([result]);setDraft('');setFiles([]);}
      await refreshConversations();
    } catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function upload(list: FileList|null) {
    if (!list) return;
    setBusy(true);setError('');
    try {
      for (const file of Array.from(list)) {
        const result = await client.files.upload(file);
        setFiles(old=>[...old,result].slice(0,10));
      }
    } catch(e) {setError((e as Error).message);} finally {setBusy(false);if(uploadRef.current)uploadRef.current.value='';}
  }
  async function download(file: AgentFile) {
    try {
      const text = await client.files.content(file.id);
      const url = URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));
      const a = document.createElement('a');a.href=url;a.download=file.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch(e) {setError((e as Error).message);}
  }
  const title = conversations.find(c=>c.id===cid)?.title || '新的开始';
  const toolEvents = events.filter(e=>e.type==='tool_call.started');

  return <div className="app">
    <aside className={`sidebar ${sidebar?'visible':''}`}>
      <div className="brand"><div className="brand-mark">栖</div><span>栖 <small>PERSONAL AGENT</small></span><button className="icon-button collapse" onClick={()=>setSidebar(false)} aria-label="收起导航"><PanelLeftClose size={17}/></button></div>
      <button className="new-chat" onClick={()=>chooseConversation(null)}><Plus size={17}/>开启新对话<span>⌘ N</span></button>
      <nav>
        <button className={page==='chat'?'selected':''} onClick={()=>setPage('chat')}><MessageSquare size={17}/>对话</button>
        <button className={page==='tasks'?'selected':''} onClick={()=>setPage('tasks')}><Activity size={17}/>执行记录</button>
        <button className={page==='skills'?'selected':''} onClick={()=>setPage('skills')}><Layers size={17}/>技能库 <span className="count">{skills.length}</span></button>
      </nav>
      <div className="section-label">最近对话</div>
      <div className="conversation-list">{conversations.length===0?<p className="empty-history">你的想法，从这里开始。</p>:conversations.map(c=><button key={c.id} className={c.id===cid?'current':''} onClick={()=>chooseConversation(c.id)}><MessageSquare size={14}/><span>{c.title}</span></button>)}</div>
      <div className="sidebar-bottom"><div className="local-status"><span className="dot"/>本地工作空间<span>v0.1</span></div><button className={page==='settings'?'selected':''} onClick={()=>setPage('settings')}><SettingsIcon size={17}/>设置与模型</button><div className="profile"><div className="avatar">我</div><div>个人空间<small>Local · Private</small></div><span className="profile-tag">本地</span></div></div>
    </aside>
    <main>
      <header><div><button className="icon-button mobile-menu" aria-label="展开导航" onClick={()=>setSidebar(!sidebar)}><Menu size={19}/></button><span className="breadcrumb">个人空间</span><ChevronRight size={13}/><strong>{page==='chat'?title:page==='skills'?'技能库':page==='settings'?'设置与模型':'执行记录'}</strong></div><span className="mode-badge"><span className="dot"/>{settings?.model||'尚未配置模型'}</span></header>
      {error&&<div className="error" role="alert">{error}<button onClick={()=>setError('')} aria-label="关闭错误"><X size={15}/></button></div>}
      {page==='settings'?<SettingsPanel value={settings} onSave={setSettings} onError={setError}/>:
      page==='skills'?<div className="content-page"><div className="eyebrow">YOUR TOOLKIT</div><button className="primary-button" style={{float:'right'}} onClick={()=>client.skills.list().then(r=>setSkills(r.items)).catch(e=>setError(e.message))}>刷新技能</button><h1>把方法，变成能力。</h1><p className="muted">Skill 为 Agent 提供可复用的工作流程，执行仍由工具完成。</p><div className="skill-grid">{skills.map(s=><article className="skill-card" key={s.id}><div className="skill-icon"><Layers size={22}/></div><span className="tag">{s.scope} · {s.source}</span><h3>{s.name==='weekly-report'?'周报生成':s.name==='document-summary'?'文档总结':s.name}</h3><p>{s.description}</p><small className="skill-source">{s.path}</small>{s.unsupported_fields.length>0&&<small className="skill-source">未启用的扩展字段：{s.unsupported_fields.join(', ')}</small>}<div className="skill-actions"><button onClick={()=>client.skills.get(s.id).then(v=>setPreview({title:s.name,content:v.content})).catch(e=>setError(e.message))}>查看说明 <ExternalLink size={13}/></button><button onClick={()=>{setSkill(s.id);setPage('chat');}}>在对话中使用 <ChevronRight size={14}/></button></div></article>)}</div><div className="note"><Sparkles size={16}/>自动发现用户与工作空间中的 .agents/skills、.claude/skills，兼容 ~/.codex/skills；正文按需加载。</div></div>:
      page==='tasks'?<TaskPanel onSelect={id=>chooseConversation(id)} onError={setError}/>:
      <><div className="chat-scroll">
        {messages.length===0&&!active(run)?<div className="welcome"><div className="welcome-symbol"><Sparkles size={30} strokeWidth={1.3}/></div><div className="eyebrow">A LITTLE SPACE FOR BIG IDEAS</div><h1>把想法交给我，<br/><span>一起把事情做好。</span></h1><p>从一份笔记、一个问题，或一项具体的工作开始。<br/>我会使用工具与技能，把过程和结果留在这里。</p><div className="suggestions"><button onClick={()=>{setSkill('document-summary');setDraft('请总结我上传的文档，保留关键结论并注明来源。');uploadRef.current?.click();}}><FileText size={20}/><strong>读懂一份文档</strong><span>提炼重点，保留依据 <ChevronRight size={13}/></span></button><button onClick={()=>{setSkill('weekly-report');setDraft('请根据我上传的笔记生成本周周报。');uploadRef.current?.click();}}><Layers size={20}/><strong>整理本周进展</strong><span>把零散笔记变成周报 <ChevronRight size={13}/></span></button><button onClick={()=>setDraft('你有哪些工具和技能？可以怎样帮助我？')}><Sparkles size={20}/><strong>认识我的能力</strong><span>探索工具与工作方式 <ChevronRight size={13}/></span></button></div></div>:
        <div className="message-list">{messages.map(m=><div className={`message ${m.role}`} key={m.id}><div className="message-avatar">{m.role==='user'?'我':'栖'}</div><div className="message-body"><div className="message-author">{m.role==='user'?'你':'栖'}<small>{new Date(m.created_at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</small></div><Markdown>{m.content}</Markdown></div></div>)}
        {toolEvents.length>0&&<details className="execution" open={!!active(run)}><summary><Activity size={15}/>执行过程 · {toolEvents.length} 次工具调用<span>{run?labels[run.status]:''}</span></summary>{toolEvents.map(e=>{const done=events.find(c=>c.type==='tool_call.completed'&&c.data.tool_call_id===e.data.tool_call_id);return <details key={e.id} className="tool-row"><summary>{done?<Check size={14}/>:<LoaderCircle className="spin" size={14}/>}<code>{String(e.data.tool_name)}</code><span>{done?(done.data.status==='failed'?'失败':'完成'):'执行中'}</span></summary><pre>{JSON.stringify({arguments:e.data.arguments,result:done?.data.result},null,2)}</pre></details>;})}</details>}
        {active(run)&&<div className="message assistant"><div className="message-avatar">栖</div><div className="message-body"><div className="message-author">栖 <small>正在处理</small></div>{live?<Markdown>{live}</Markdown>:<span className="thinking">正在思考与执行<span>•••</span></span>}</div></div>}
        {events.some(e=>e.type==='context.built')&&<button className="context-button" onClick={()=>setPreview({title:'本次上下文清单',content:'```json\n'+JSON.stringify(events.find(e=>e.type==='context.built')?.data,null,2)+'\n```'})}>查看本次上下文与环境信息</button>}
        {run?.error&&<div className="run-error">{run.error}</div>}
        {artifacts.length>0&&<div className="artifact-list">{artifacts.map(f=><div className="artifact" key={f.id}><FileText size={24}/><button onClick={()=>client.files.content(f.id).then(content=>setPreview({title:f.name,content})).catch(e=>setError(e.message))}><strong>{f.name}</strong><small>Markdown 产物 · {(f.size/1024).toFixed(1)} KB · 点击预览</small></button><button className="icon-button" aria-label={`下载 ${f.name}`} onClick={()=>download(f)}><Download size={17}/></button></div>)}</div>}
        </div>}
        <div ref={bottom}/>
      </div>
      <div className="composer-wrap"><div className="composer">
        {files.length>0&&<div className="attachments">{files.map(f=><span key={f.id}><FileText size={14}/>{f.name}<button aria-label={`移除 ${f.name}`} onClick={()=>setFiles(old=>old.filter(v=>v.id!==f.id))}><X size={13}/></button></span>)}</div>}
        <textarea value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send();}}} placeholder="交代一件事，或一起聊聊你的想法…" aria-label="消息" rows={2}/>
        <div className="composer-toolbar"><div><button className="icon-button" title="上传文本文件（最大60KB）" aria-label="上传文件" disabled={busy||!!active(run)} onClick={()=>uploadRef.current?.click()}><Paperclip size={19}/></button><span className="divider"/><Layers size={15}/><select aria-label="选择技能" value={skill} onChange={e=>setSkill(e.target.value)}><option value="">自动选择技能</option>{skills.map(s=><option key={s.id} value={s.id}>{s.name==='weekly-report'?'周报生成':s.name==='document-summary'?'文档总结':s.name}</option>)}</select></div><div><small>Enter 发送</small>{active(run)?<button className="send-button" aria-label="停止执行" onClick={()=>client.runs.cancel(run.id).then(r=>setRuns(old=>[r,...old.slice(1)])).catch(e=>setError(e.message))}><Square size={15}/></button>:<button className="send-button" aria-label="发送消息" onClick={()=>void send()} disabled={!draft.trim()||busy}>{busy?<LoaderCircle className="spin" size={18}/>:<ArrowUp size={20}/>}</button>}</div></div>
      </div><p className="composer-footnote">模型可能出错，请核实重要信息。 <button onClick={()=>setPage('settings')}>模型设置 <ChevronRight size={11}/></button></p></div></>}
    </main>
    <input type="file" ref={uploadRef} hidden multiple accept=".md,.txt,.csv,.json,.log" onChange={e=>void upload(e.target.files)}/>
    {preview&&<div className="modal-backdrop" onClick={()=>setPreview(null)}><section className="preview-modal" role="dialog" aria-modal="true" aria-label={preview.title} onClick={e=>e.stopPropagation()}><div className="modal-header"><FileText size={18}/><strong>{preview.title}</strong><button className="icon-button" aria-label="关闭预览" onClick={()=>setPreview(null)}><X size={19}/></button></div><div className="markdown-preview"><Markdown>{preview.content}</Markdown></div></section></div>}
  </div>;
}

function SettingsPanel({value,onSave,onError}:{value:Settings|null;onSave:(s:Settings)=>void;onError:(e:string)=>void}) {
  const [url,setUrl]=useState(value?.base_url||'https://api.openai.com/v1');
  const [model,setModel]=useState(value?.model||'');
  const [timezone,setTimezone]=useState(value?.timezone||'Asia/Shanghai');
  const [instructionMode,setInstructionMode]=useState<'auto'|'codex'|'claude'>(value?.instruction_mode||'auto');
  const [discovery,setDiscovery]=useState<{instructions:{path:string}[];warnings:string[]}|null>(null);
  useEffect(()=>{client.discovery().then(setDiscovery).catch(e=>onError(e.message));},[]);
  const [key,setKey]=useState('');
  const [saving,setSaving]=useState(false);
  const [saved,setSaved]=useState(false);
  const [clearKey,setClearKey]=useState(false);
  async function save(e:React.FormEvent){e.preventDefault();setSaving(true);setSaved(false);try{const result=await client.settings.save({base_url:url,model,timezone,instruction_mode:instructionMode,api_key:clearKey?'':key||null});onSave(result);setKey('');setClearKey(false);setSaved(true);setDiscovery(await client.discovery());}catch(e){onError((e as Error).message);}finally{setSaving(false);}}
  return <div className="content-page settings-page"><div className="eyebrow">MAKE IT YOURS</div><h1>连接你的模型。</h1><p className="muted">在这里配置，所有客户端共用同一个 Agent 后端。</p><form className="settings-form" onSubmit={save}><label>工作空间<input readOnly value={value?.workspace_path||''}/><small>规则和项目级技能从此目录加载。通过服务启动配置 AGENT_WORKSPACE 指定。</small></label><label>时区<input value={timezone} onChange={e=>setTimezone(e.target.value)} required placeholder="Asia/Shanghai"/><small>每次执行按该时区计算日期和星期。</small></label><label>规则文件兼容<select value={instructionMode} onChange={e=>setInstructionMode(e.target.value as 'auto'|'codex'|'claude')}><option value="auto">自动：优先 AGENTS.md，缺失时使用 CLAUDE.md</option><option value="codex">Codex：AGENTS.override.md / AGENTS.md</option><option value="claude">Claude：CLAUDE.md</option></select></label>{discovery&&<div className="discovery-info"><strong>当前加载的规则</strong>{discovery.instructions.length?discovery.instructions.map(r=><p key={r.path}>{r.path}</p>):<p>未发现规则文件；可在工作空间中创建 AGENTS.md。</p>}{discovery.warnings.map(w=><p key={w}>{w}</p>)}</div>}<label>模型服务地址 <input value={url} onChange={e=>{setUrl(e.target.value);setSaved(false);}} required type="url" placeholder="https://api.example.com/v1"/><small>填写 API Base URL，需支持流式回复和工具调用。</small></label><label>模型名称<input value={model} onChange={e=>setModel(e.target.value)} required placeholder="填写服务商提供的模型 ID"/></label><label>API 密钥<span className="key-status">{value?.has_api_key?'已保存密钥':'尚未配置'}</span><input type="password" autoComplete="new-password" value={key} onChange={e=>{setKey(e.target.value);setClearKey(false);}} placeholder={value?.has_api_key?'留空保留现有密钥':'输入 API Key'}/><small>密钥仅保存在本机后端，不回传到页面，不写入 Git。请求会将任务材料发送到你配置的模型服务。</small></label>{value?.has_api_key&&<label className="checkbox-label"><input type="checkbox" checked={clearKey} onChange={e=>setClearKey(e.target.checked)}/>清除已保存密钥（清除后需重新配置才能使用）</label>}<div className="form-footer"><span>{saved?<><Check size={15}/>配置已保存</>:'更换服务地址时，请重新输入对应密钥。'}</span><button className="primary-button" disabled={saving} type="submit">{saving?'保存中…':'保存配置'}</button></div></form><div className="note"><SettingsIcon size={16}/>当前配置为本机单用户使用。首版不包含定时调度、跨重启任务续跑和桌面壳。</div></div>;
}

function TaskPanel({onSelect,onError}:{onSelect:(id:string)=>void;onError:(error:string)=>void}) {
  const [runs,setRuns]=useState<Run[]>([]);
  useEffect(()=>{let closed=false;const load=()=>client.runs.list().then(r=>{if(!closed)setRuns(r.items);}).catch(e=>{if(!closed)onError(e.message);});void load();const timer=setInterval(()=>void load(),3000);return()=>{closed=true;clearInterval(timer);};},[]);
  return <div className="content-page"><div className="eyebrow">WORK IN MOTION</div><h1>每一步，都有迹可循。</h1><p className="muted">查看真实执行状态，回到对话继续工作。</p><div className="task-list">{runs.length===0?<div className="empty-panel"><Activity size={28}/><p>还没有执行记录。发起一段对话，开始第一项任务。</p></div>:runs.map(r=><button key={r.id} className="task-item" onClick={()=>onSelect(r.conversation_id)}><Activity size={20}/><div><strong>{r.skill_id||'Agent 任务'}</strong><small>{new Date(r.created_at).toLocaleString('zh-CN')} · {r.id.slice(0,12)}</small></div><span className={`status ${r.status}`}>{labels[r.status]}</span><ChevronRight size={16}/></button>)}</div></div>;
}

createRoot(document.getElementById('root')!).render(<App/>);
