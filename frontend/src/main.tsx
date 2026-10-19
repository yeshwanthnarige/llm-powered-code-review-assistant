import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowRight, BookOpen, Check, ChevronRight, CircleDot, Code2, FileCode2, GitPullRequest, History, Layers3, Loader2, MessageSquare, Plus, SearchCode, ShieldCheck, ThumbsDown, ThumbsUp, Upload, X } from 'lucide-react';
import './styles.css';

type Source = {path: string; content: string};
type Chunk = Source & {id: string; start: number; end: number; score: number};
type Finding = {path: string; line: number; severity: 'high'|'medium'|'low'; title: string; explanation: string; suggestion: string; context_ids: string[]; helpful: boolean|null};
type DiffFile = {path: string; added_lines: number[]; lines: {kind: string; number: number|null; text: string}[]};
type Review = {id: string; title: string; project: string; summary: string; findings: Finding[]; context: Chunk[]; files: DiffFile[]; warnings: string[]; provider: string; created_at: string};
type HistoryItem = {id: string; title: string; findings: number; created_at: string; provider: string};
type Health = {provider: string; model: string; embedding: string; database: string};

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, body === undefined ? undefined : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check your inputs. Files must be plain text with valid relative paths.');
  return data;
}

function App() {
  const [health, setHealth] = useState<Health|null>(null);
  const [project, setProject] = useState('acme/checkout');
  const [title, setTitle] = useState('');
  const [diff, setDiff] = useState('');
  const [prUrl, setPrUrl] = useState('');
  const [tab, setTab] = useState<'paste'|'github'>('paste');
  const [view, setView] = useState<'review'|'context'|'history'>('review');
  const [result, setResult] = useState<Review|null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [inventory, setInventory] = useState<{files: string[]; chunks: number}>({files: [], chunks: 0});
  const [sources, setSources] = useState<Source[]>([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [activeFile, setActiveFile] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);

  async function refresh(key: string) {
    const [items, index] = await Promise.all([
      api<HistoryItem[]>('/reviews?project=' + encodeURIComponent(key)),
      api<{files: string[]; chunks: number}>('/projects/' + encodeURIComponent(key) + '/index'),
    ]);
    setHistory(items); setInventory(index);
  }
  useEffect(() => { api<Health>('/health').then(setHealth).catch(() => setError('The API is unavailable. Start the Python server, then refresh.')); }, []);
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      Promise.all([api<HistoryItem[]>('/reviews?project=' + encodeURIComponent(project)), api<{files: string[]; chunks: number}>('/projects/' + encodeURIComponent(project) + '/index')])
        .then(([items, index]) => { if (!cancelled) {setHistory(items); setInventory(index);} })
        .catch(() => { if (!cancelled) {setHistory([]); setInventory({files: [], chunks: 0});} });
    }, 250);
    return () => {cancelled = true; clearTimeout(timer);};
  }, [project]);

  async function action(label: string, task: () => Promise<void>) {
    setBusy(label); setError(''); setNotice('');
    try { await task(); } catch (e) { setError(e instanceof Error ? e.message : 'Something went wrong. Please retry.'); }
    finally { setBusy(''); }
  }

  async function loadExample() {
    await action('Loading example', async () => {
      const sample = await api<{project: string; title: string; diff: string; files: Source[]}>('/sample');
      setProject(sample.project); setTitle(sample.title); setDiff(sample.diff); setSources(sample.files);
      setResult(null); setTab('paste'); setView('review');
      setNotice('Example loaded. Index its two context files from Codebase, then run a review.');
    });
  }

  async function runReview() {
    await action('Retrieving context and reviewing changes', async () => {
      const review = await api<Review>('/reviews', {project, title: title || 'Untitled review', diff});
      setResult(review); setActiveFile(0); await refresh(project);
    });
  }

  async function uploadFiles(files: FileList|null) {
    if (!files) return;
    await action('Reading source files', async () => {
      if (files.length + sources.length > 40) throw new Error('Select at most 40 files.');
      const next = await Promise.all(Array.from(files).map(async f => {
        if (f.size > 50000) throw new Error(f.name + ' exceeds 50 KB.');
        const content = await f.text();
        if (content.includes('\0')) throw new Error(f.name + ' is not a text file.');
        return {path: f.webkitRelativePath || f.name, content};
      }));
      setSources([...sources, ...next]);
    });
    if (fileInput.current) fileInput.current.value = '';
  }

  const reviewedVotes = result?.findings.filter(f => f.helpful !== null) || [];
  const selected = result?.files[activeFile];

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="ReviewLens home"><span className="brand-mark"><SearchCode size={22}/></span>ReviewLens<span className="beta">BETA</span></a>
      <div className="workspace-label">YOUR WORKSPACE</div>
      <nav aria-label="Main navigation">
        <button className={view === 'review' ? 'nav active' : 'nav'} onClick={() => setView('review')}><GitPullRequest size={18}/> Review changes <ChevronRight size={14}/></button>
        <button className={view === 'context' ? 'nav active' : 'nav'} onClick={() => setView('context')}><Layers3 size={18}/> Codebase <span className="nav-count">{inventory.files.length}</span></button>
        <button className={view === 'history' ? 'nav active' : 'nav'} onClick={() => setView('history')}><History size={18}/> Review history <span className="nav-count">{history.length}</span></button>
      </nav>
      <div className="sidebar-project"><span className="workspace-label">CURRENT PROJECT</span><label htmlFor="project">Repository name</label><input id="project" value={project} disabled={!!busy} onChange={e => {setProject(e.target.value); setResult(null); setSources([]);}}/><div className="project-status"><span/> {inventory.chunks} context chunks indexed</div></div>
      <div className="sidebar-bottom"><div className="local-badge"><ShieldCheck size={17}/> Your review, your decision</div><p>Suggestions are advisory. Inspect the evidence and run your tests.</p><div className="profile"><span>YN</span><div>Personal workspace<small>Local development</small></div></div></div>
    </aside>
    <main>
      <header className="topbar"><div>Workspace <ChevronRight size={13}/> <strong>{view === 'review' ? 'Review changes' : view === 'context' ? 'Codebase' : 'Review history'}</strong></div><span className="mode-pill"><span/>{health ? health.provider === 'demo' ? 'Demo mode' : 'OpenAI connected' : 'Connecting'}</span></header>
      <div className="page">
        <div className="page-heading"><div><div className="eyebrow">CODE REVIEW, WITH CONTEXT</div><h1>{view === 'review' ? result ? 'A closer look at your changes.' : 'Less noise. More context.' : view === 'context' ? 'Give your review the full picture.' : 'Every review, in one place.'}</h1><p>{view === 'review' ? 'Actionable feedback grounded in the code that surrounds your changes.' : view === 'context' ? 'Index source files and team conventions to make suggestions relevant.' : 'Revisit findings, evidence, and the feedback you collected.'}</p></div><button className="button secondary" disabled={!!busy} onClick={loadExample}><Code2 size={16}/> Load example</button></div>
        {health?.provider === 'demo' && <div className="demo-banner"><CircleDot size={16}/><span><strong>You’re in demo mode.</strong> Local pattern checks and hashed retrieval. Enable OpenAI in your server configuration for LLM reviews.</span><span className="small-label">NO API KEY NEEDED</span></div>}
        {error && <div className="alert error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={15}/></button></div>}
        {notice && <div className="alert notice" role="status">{notice}<button aria-label="Dismiss notice" onClick={() => setNotice('')}><X size={15}/></button></div>}
        {busy && <div className="progress" role="status"><Loader2 size={16} className="spin"/>{busy}…</div>}

        {view === 'review' && !result && <>
          <div className="steps"><span className="step current"><b>1</b> Add your changes</span><i/><span className="step"><b>2</b> Retrieve context</span><i/><span className="step"><b>3</b> Review the evidence</span></div>
          <div className="compose-grid"><section className="card compose"><div className="card-heading"><div><GitPullRequest size={19}/><h2>New review</h2></div><span className="small-label">READ-ONLY ANALYSIS</span></div><div className="tabs"><button className={tab === 'paste' ? 'selected' : ''} onClick={() => setTab('paste')}>Paste a diff</button><button className={tab === 'github' ? 'selected' : ''} onClick={() => setTab('github')}>Import pull request</button></div>
            {tab === 'github' && <div className="github-import"><label htmlFor="pr-url">GitHub pull request URL</label><div className="input-action"><input id="pr-url" placeholder="https://github.com/owner/repo/pull/123" value={prUrl} onChange={e => setPrUrl(e.target.value)}/><button className="button secondary" disabled={!!busy || !prUrl} onClick={() => action('Importing pull request', async () => {const imported = await api<{project: string; title: string; diff: string}>('/github/import', {url: prUrl}); setProject(imported.project); setTitle(imported.title); setDiff(imported.diff); setSources([]); setTab('paste'); setNotice('Diff imported. Add source files in Codebase for repository context.');})}>Import</button></div><small>Imports the diff only. Private repositories require a server-side GitHub token.</small></div>}
            <label htmlFor="review-title">Review title</label><input id="review-title" placeholder="e.g. Add checkout preferences" value={title} onChange={e => setTitle(e.target.value)} maxLength={160}/>
            <div className="label-row"><label htmlFor="diff">Unified diff</label><span>git diff main...HEAD</span></div><textarea id="diff" className="diff-input" spellCheck={false} value={diff} onChange={e => setDiff(e.target.value)} placeholder={'diff --git a/src/api.py b/src/api.py\n--- a/src/api.py\n+++ b/src/api.py\n@@ -1 +1 @@\n- previous_behavior()\n+ updated_behavior()'}/>
            <div className="compose-footer"><span><ShieldCheck size={14}/> No code is executed or modified</span><button className="button primary" disabled={!!busy || !diff.trim() || !project.trim()} onClick={runReview}>Run review <ArrowRight size={16}/></button></div>
          </section><div className="right-stack"><section className="card context-summary"><span className="icon-square"><Layers3 size={21}/></span><h2>Better context.<br/>Better feedback.</h2><p>Bring in related functions, contracts, and conventions. ReviewLens retrieves the relevant pieces for each review.</p><div className="context-stats"><div><strong>{inventory.files.length}</strong><span>source files</span></div><div><strong>{inventory.chunks}</strong><span>indexed chunks</span></div></div><button className="text-button" onClick={() => setView('context')}>Manage codebase <ArrowRight size={15}/></button></section><div className="tip"><BookOpen size={19}/><div><strong>Start small, review deeply.</strong><p>A focused diff gives you more useful feedback. Start with a single feature or bug fix.</p></div></div></div></div>
        </>}

        {view === 'review' && result && <>
          <div className="result-toolbar"><div><span className="tag">{result.provider === 'demo' ? 'DEMO REVIEW' : 'LLM REVIEW'}</span><h2>{result.title}</h2></div><button className="button secondary" disabled={!!busy} onClick={() => setResult(null)}><Plus size={15}/> New review</button></div>
          <div className="metrics"><div><MessageSquare size={19}/><strong>{result.findings.length}</strong><span>findings to inspect</span></div><div><FileCode2 size={19}/><strong>{result.files.length}</strong><span>changed files</span></div><div><Layers3 size={19}/><strong>{result.context.length}</strong><span>retrieved snippets</span></div><div><ThumbsUp size={19}/><strong>{reviewedVotes.length ? Math.round(reviewedVotes.filter(f => f.helpful).length / reviewedVotes.length * 100) + '%' : '—'}</strong><span>{reviewedVotes.length ? `${reviewedVotes.length} rated suggestions` : 'no feedback yet'}</span></div></div>
          <p className="review-summary">{result.summary}</p>{result.warnings.map(w => <div key={w} className="alert warning">{w}</div>)}
          <div className="review-grid"><section className="card code-panel"><div className="card-heading"><div><Code2 size={17}/><h2>Changed code</h2></div><span className="small-label">NEW-SIDE LINES</span></div><div className="file-tabs">{result.files.map((f, i) => <button key={f.path} className={activeFile === i ? 'selected' : ''} onClick={() => setActiveFile(i)}><FileCode2 size={14}/>{f.path}</button>)}</div><div className="code-scroll">{selected?.lines.map((line, i) => <div key={i} className={'code-line ' + (line.kind === '+' ? 'added' : line.kind === '-' ? 'removed' : '') + (result.findings.some(f => f.path === selected.path && f.line === line.number) ? ' flagged' : '')}><span className="line-number">{line.number ?? ''}</span><span className="line-sign">{line.kind}</span><code>{line.text || ' '}</code></div>)}</div><div className="code-legend"><span className="green-dot"/> Added <span className="red-dot"/> Removed <span className="purple-dot"/> Finding</div></section>
          <section className="findings"><div className="findings-heading"><h2>Review findings</h2><span>{result.findings.length}</span></div>{result.findings.length === 0 && <div className="card empty-findings"><Check size={26}/><h3>No supported findings</h3><p>This does not prove the change is correct. Run your tests and inspect the diff.</p></div>}{result.findings.map((f, i) => <article className="card finding" key={i}><div className="finding-meta"><span className={'severity ' + f.severity}>{f.severity} priority</span><button className="location" onClick={() => setActiveFile(result.files.findIndex(file => file.path === f.path))}>{f.path}:{f.line}</button></div><h3>{f.title}</h3><p>{f.explanation}</p><div className="suggestion"><strong>Suggested change</strong><p>{f.suggestion}</p></div>{f.context_ids.length > 0 && <div className="citations">Evidence: {f.context_ids.map(id => {const c = result.context.find(c => c.id === id); return c && <a key={id} href={'#context-' + id}>{c.path}:{c.start}</a>;})}</div>}<div className="feedback"><span>Was this useful?</span><button aria-label={'Mark finding ' + (i + 1) + ' helpful'} aria-pressed={f.helpful === true} disabled={!!busy} onClick={() => action('Saving feedback', async () => setResult(await api<Review>(`/reviews/${result.id}/findings/${i}/feedback`, {helpful: true})))}><ThumbsUp size={14}/> Yes</button><button aria-label={'Mark finding ' + (i + 1) + ' not helpful'} aria-pressed={f.helpful === false} disabled={!!busy} onClick={() => action('Saving feedback', async () => setResult(await api<Review>(`/reviews/${result.id}/findings/${i}/feedback`, {helpful: false})))}><ThumbsDown size={14}/> No</button></div></article>)}</section></div>
          <section className="evidence-section"><h2><Layers3 size={18}/> Retrieved context</h2><p>These snippets were available to the reviewer. A finding cites a snippet only when the model links it as supporting evidence.</p>{result.context.map(c => <details className="card evidence" id={'context-' + c.id} key={c.id}><summary><FileCode2 size={16}/><strong>{c.path}</strong><span>Lines {c.start}–{c.end}</span><span className="score">Similarity {c.score.toFixed(2)}</span></summary><pre>{c.content}</pre></details>)}</section>
        </>}

        {view === 'context' && <div className="context-page"><section className="card"><div className="card-heading"><div><Layers3 size={19}/><h2>Source context</h2></div><span className="small-label">{inventory.chunks} CHUNKS INDEXED</span></div><p className="muted">Choose relevant source files, tests, or conventions. Edit the relative paths before indexing. Reindexing a path replaces its previous chunks.</p><input ref={fileInput} type="file" multiple hidden onChange={e => uploadFiles(e.target.files)}/><button className="upload-zone" disabled={!!busy} onClick={() => fileInput.current?.click()}><Upload size={26}/><strong>Choose source files</strong><span>Plain text · up to 40 files · 50 KB per file</span></button>{sources.map((s, i) => <div className="source-row" key={i}><FileCode2 size={17}/><input aria-label={'Path for source ' + (i + 1)} value={s.path} onChange={e => setSources(sources.map((item, j) => j === i ? {...item, path: e.target.value} : item))}/><span>{s.content.split('\n').length} lines</span><button aria-label={'Remove source ' + (i + 1)} disabled={!!busy} onClick={() => setSources(sources.filter((_, j) => j !== i))}><X size={16}/></button></div>)}<div className="index-footer"><span>{health?.provider === 'openai' ? 'Selected file contents are sent to OpenAI for embeddings.' : 'Demo indexing runs locally; no external model calls.'}</span><button className="button primary" disabled={!!busy || !sources.length || !project} onClick={() => action('Indexing source context', async () => {await api('/index', {project, files: sources}); await refresh(project); setSources([]); setNotice('Source files indexed. Your next review will retrieve matching context.');})}>Index {sources.length || ''} files <ArrowRight size={16}/></button></div></section><section className="card indexed"><h2>Indexed files</h2>{inventory.files.length ? inventory.files.map(path => <div key={path}><FileCode2 size={16}/>{path}<Check size={15}/></div>) : <p className="muted">No source files yet. Load the example or choose your own files.</p>}</section></div>}

        {view === 'history' && <section className="card history-card"><div className="card-heading"><div><History size={19}/><h2>Recent reviews</h2></div><span className="small-label">LATEST 50 · {project}</span></div>{history.length ? history.map(item => <button key={item.id} className="history-row" disabled={!!busy} onClick={() => action('Opening review', async () => {setResult(await api<Review>('/reviews/' + item.id)); setActiveFile(0); setView('review');})}><span className="history-icon"><GitPullRequest size={19}/></span><div><strong>{item.title}</strong><small>{new Date(item.created_at).toLocaleString()} · {item.provider === 'demo' ? 'Demo' : 'OpenAI'}</small></div><span>{item.findings} findings</span><ChevronRight size={17}/></button>) : <div className="empty-history"><History size={32}/><h3>Your first review starts here.</h3><p>Run a review to save its findings and evidence.</p><button className="button primary" onClick={() => setView('review')}>Create a review <ArrowRight size={16}/></button></div>}</section>}
        <footer className="page-footer"><span>ReviewLens <span className="footer-dot">·</span> Built for thoughtful code review</span><span>{health?.database === 'postgresql' ? 'PostgreSQL + pgvector' : 'SQLite local storage'} <span className="footer-dot">·</span> Human judgment, always</span></footer>
      </div>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
