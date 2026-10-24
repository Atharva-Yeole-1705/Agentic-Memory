import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const suggestions = [
  { title: "Build something", text: "Help me plan and build a small Python project." },
  { title: "Fix an error", text: "I have an error I can't figure out. Can you help me debug it?" },
  { title: "Explain code", text: "Explain the difference between a list and a tuple in Python." },
  { title: "Review an idea", text: "Review a simple FastAPI endpoint architecture and suggest a clean approach." },
];

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || "The request failed. Try again.");
  return result;
}

function Icon({ name, size = 18 }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };
  const paths = {
    plus: <><path d="M12 5v14M5 12h14" /></>,
    message: <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.7-3.3A7.5 7.5 0 1 1 20 11.5Z" /><path d="M9 11h.01M12.5 11h.01M16 11h.01" /></>,
    code: <><path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14" /></>,
    send: <><path d="m21 3-7.5 18-3.7-7.8L2 9.5 21 3Z" /><path d="M9.8 13.2 21 3" /></>,
    spark: <><path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z" /><path d="m19 16 .8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z" /></>,
    panel: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" /></>,
    arrow: <><path d="M7 17 17 7M7 7h10v10" /></>,
    chevron: <><path d="m9 18 6-6-6-6" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function Sidebar({ sessions, activeId, onNew, onSelect, status, mobileOpen, onClose, busy }) {
  return (
    <>
      {mobileOpen && <button className="mobile-scrim" onClick={onClose} aria-label="Close menu" />}
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark"><Icon name="code" size={20} /></div>
          <span className="brand-name">recall<span>.</span></span>
          <button className="icon-button sidebar-close" onClick={onClose} aria-label="Close sidebar"><Icon name="panel" /></button>
        </div>

        <button className="new-chat" onClick={onNew} disabled={busy}>
          <Icon name="plus" size={17} /><span>New conversation</span><kbd>Ctrl K</kbd>
        </button>

        <div className="section-label">YOUR WORKSPACE</div>
        <div className="nav-item nav-active"><Icon name="message" size={17} /><span>Conversations</span><span className="nav-count">{sessions.length}</span></div>

        <div className="history-heading"><span>RECENT</span><button className="quiet-button" onClick={onNew}>New</button></div>
        <div className="session-list">
          {sessions.map((session) => (
            <button key={session.id} className={`session-item ${activeId === session.id ? "session-active" : ""}`} onClick={() => onSelect(session.id)} disabled={busy}>
              <span className="session-icon"><Icon name="message" size={15} /></span>
              <span className="session-copy"><span className="session-title">{session.title || "New conversation"}</span><span className="session-meta">{session.message_count} messages</span></span>
              {activeId === session.id && <span className="active-dot" />}
            </button>
          ))}
          {!sessions.length && <div className="empty-history">Your conversations will appear here.</div>}
        </div>

        <div className="sidebar-bottom">
          <div className="memory-card">
            <div className="memory-card-top"><span className="memory-icon"><Icon name="spark" size={16} /></span><span className="memory-label">LONG-TERM MEMORY</span><span className={`online-dot ${status ? "" : "offline-dot"}`} /></div>
            <p>{status?.summarizer_only ? "Summariser-only mode" : "Relevant context, remembered."}</p>
            <span className="memory-caption">MongoDB <i>&middot;</i> Voyage AI <i>&middot;</i> top 8</span>
          </div>
          <div className="profile-row"><div className="profile-avatar">A</div><div className="profile-copy"><strong>Local workspace</strong><span>MongoDB on this machine</span></div><span className="profile-menu">...</span></div>
        </div>
      </aside>
    </>
  );
}

function Message({ message }) {
  const isUser = message.role === "user";
  return (
    <article className={`message-row ${isUser ? "message-user" : "message-assistant"}`}>
      {!isUser && <div className="assistant-avatar"><Icon name="code" size={16} /></div>}
      <div className="message-content">
        {!isUser && <div className="message-author">Recall <span>&middot;</span> Coding assistant</div>}
        <div className={`message-bubble ${isUser ? "user-bubble" : "assistant-bubble"}`}>
          {isUser ? <p>{message.content}</p> : <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>}
        </div>
      </div>
      {isUser && <div className="user-avatar">Y</div>}
    </article>
  );
}

function MultiSelectFilter({ title, allLabel, options, selected, onChange }) {
  const allSelected = selected.length === 0 || selected.length === options.length;
  const selectedOptions = options.filter((option) => selected.includes(option.value));
  const valueLabel = allSelected
    ? allLabel
    : selectedOptions.length === 1
      ? selectedOptions[0].label
      : `${selectedOptions.length} selected`;

  function toggle(value) {
    const next = selected.includes(value)
      ? selected.filter((item) => item !== value)
      : [...selected, value];
    onChange(next.length === options.length ? [] : next);
  }

  return (
    <details className={`filter-dropdown filter-${title.toLowerCase()}`}>
      <summary>
        <span className="filter-name">{title}</span>
        <span className="filter-value" title={valueLabel}>{valueLabel}</span>
        <Icon name="chevron" size={13} />
      </summary>
      <div className="filter-menu">
        <button
          type="button"
          className={`filter-option filter-all-option ${allSelected ? "filter-option-selected" : ""}`}
          aria-pressed={allSelected}
          onClick={() => onChange([])}
        >
          <span className="filter-checkmark">{allSelected && <Icon name="check" size={12} />}</span>
          <span>{allLabel}</span>
        </button>
        <div className="filter-divider" />
        {options.map((option) => (
          <label className="filter-option" key={option.value}>
            <input
              type="checkbox"
              checked={selected.includes(option.value)}
              onChange={() => toggle(option.value)}
            />
            <span className="filter-option-copy">
              <span>{option.label}</span>
              {option.detail && <small>{option.detail}</small>}
            </span>
          </label>
        ))}
        {!options.length && <span className="filter-empty">No options available</span>}
      </div>
    </details>
  );
}

function MemoryUpdate({ output }) {
  let memories = [];
  try { memories = JSON.parse(output).memories || []; } catch { /* Keep invalid output readable below. */ }
  return (
    <details className="memory-update">
      <summary><span className="update-check"><Icon name="check" size={13} /></span><span>Memory context updated</span><span className="update-count">{memories.length} {memories.length === 1 ? "item" : "items"}</span><Icon name="chevron" size={15} /></summary>
      <div className="memory-update-body">
        {memories.length ? memories.map((memory, index) => <div className="memory-entry" key={`${memory.type}-${index}`}><span>{memory.type.replaceAll("_", " ")}</span><p>{memory.content}</p></div>) : <p className="empty-memory">No durable memory was retained for this turn.</p>}
      </div>
    </details>
  );
}

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState(null);
  const [memoryOutput, setMemoryOutput] = useState(null);
  const [selectedSources, setSelectedSources] = useState([]);
  const [selectedTypes, setSelectedTypes] = useState([]);
  const [recencyPreset, setRecencyPreset] = useState("forever");
  const [customDays, setCustomDays] = useState("30");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const textareaRef = useRef(null);
  const bottomRef = useRef(null);
  const invalidCustomDays = recencyPreset === "custom"
    && (!/^\d+$/.test(customDays) || Number(customDays) < 1);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [statusResult, sessionResult] = await Promise.all([api("/status"), api("/sessions")]);
        if (!mounted) return;
        setStatus(statusResult);
        setSessions(sessionResult.sessions);
        if (sessionResult.sessions.length) {
          const current = await api(`/sessions/${sessionResult.sessions[0].id}`);
          if (mounted) {
            setActiveId(current.id);
            setMessages(current.messages || []);
          }
        } else {
          const current = await api("/sessions", { method: "POST" });
          if (mounted) {
            setActiveId(current.id);
            setMessages([]);
            setSessions([{ id: current.id, title: "New conversation", message_count: 0 }, ...sessionResult.sessions]);
          }
        }
      } catch (requestError) {
        if (mounted) setError(requestError.message);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy, memoryOutput]);

  useEffect(() => {
    function onShortcut(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        createConversation();
      }
    }
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, [busy]);

  async function refreshSessions() {
    const result = await api("/sessions");
    setSessions(result.sessions);
  }

  async function createConversation() {
    if (busy) return;
    try {
      const session = await api("/sessions", { method: "POST" });
      setActiveId(session.id);
      setMessages([]);
      setMemoryOutput(null);
      setError("");
      setSessions((current) => [{ id: session.id, title: "New conversation", message_count: 0 }, ...current]);
      setMobileOpen(false);
      textareaRef.current?.focus();
    } catch (requestError) { setError(requestError.message); }
  }

  async function selectConversation(id) {
    if (busy) return;
    try {
      const session = await api(`/sessions/${id}`);
      setActiveId(id);
      setMessages(session.messages || []);
      setMemoryOutput(null);
      setError("");
      setMobileOpen(false);
    } catch (requestError) { setError(requestError.message); }
  }

  async function sendMessage(value = draft) {
    const content = value.trim();
    if (!content || busy || !activeId || invalidCustomDays) return;
    const previous = messages;
    setMessages([...previous, { role: "user", content }]);
    setDraft("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setBusy(true);
    setError("");
    setMemoryOutput(null);
    try {
      const result = await api(`/sessions/${activeId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content,
          memory_filters: {
            sources: selectedSources,
            types: selectedTypes,
            recency_days: recencyPreset === "forever"
              ? null
              : recencyPreset === "custom" ? Number(customDays) : Number(recencyPreset),
          },
        }),
      });
      setMessages(result.messages || []);
      setMemoryOutput(result.summarizer_output);
      if (result.memory_error) setError(`Assistant replied, but memory could not be saved: ${result.memory_error}`);
      if (result.summarizer_only) setStatus((current) => ({ ...current, summarizer_only: true }));
      try { await refreshSessions(); } catch { /* Keep the completed reply if history refresh fails. */ }
    } catch (requestError) {
      setMessages(previous);
      setDraft(content);
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  function onComposerKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  const hasMessages = messages.length > 0;
  const sourceOptions = sessions.map((session) => ({
    value: session.id,
    label: session.title || "New conversation",
    detail: session.id,
  }));
  const typeOptions = (status?.memory_types || []).map((type) => ({
    value: type,
    label: type.replaceAll("_", " "),
  }));

  return (
    <div className="app-shell">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onNew={createConversation}
        onSelect={selectConversation}
        status={status}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        busy={busy}
      />
      <main className="main-panel">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button menu-toggle" onClick={() => setMobileOpen(true)} aria-label="Open sidebar"><Icon name="panel" /></button>
            <div className="breadcrumb"><span>Workspace</span><Icon name="chevron" size={14} /><strong>Coding assistant</strong></div>
          </div>
          <div className="topbar-right">
            <span className="model-pill"><span className={`model-dot ${status ? "" : "model-dot-offline"}`} /> Groq <i>&middot;</i> Voyage</span>
            <div className="top-avatar">A</div>
          </div>
        </header>

        <div className="filter-toolbar" aria-label="Memory retrieval filters">
          <span className="filter-toolbar-title">Memory filters</span>
          <MultiSelectFilter
            title="Source"
            allLabel="All conversations"
            options={sourceOptions}
            selected={selectedSources}
            onChange={setSelectedSources}
          />
          <MultiSelectFilter
            title="Type"
            allLabel="All types"
            options={typeOptions}
            selected={selectedTypes}
            onChange={setSelectedTypes}
          />
          <label className="recency-filter">
            <span>Recency</span>
            <select value={recencyPreset} onChange={(event) => setRecencyPreset(event.target.value)}>
              <option value="forever">Forever</option>
              <option value="1">Past day</option>
              <option value="7">Past 7 days</option>
              <option value="14">Past 14 days</option>
              <option value="30">Past 30 days</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          {recencyPreset === "custom" && (
            <label className="custom-days-filter">
              <span>Days</span>
              <input
                type="number"
                min="1"
                step="1"
                value={customDays}
                onChange={(event) => setCustomDays(event.target.value)}
                aria-label="Custom recency in days"
              />
            </label>
          )}
          <span className="filter-hint">Applied to the next message</span>
        </div>

        <section className={`chat-scroll ${hasMessages ? "chat-scroll-filled" : ""}`}>
          <div className="conversation">
            {loading ? <div className="loading-state"><span className="spinner" />Connecting to your workspace...</div> : null}
            {!loading && !hasMessages && (
              <div className="welcome">
                <div className="welcome-orbit"><span /><i /><b><Icon name="code" size={23} /></b></div>
                <div className="eyebrow"><span /> YOUR PERSONAL CODING PARTNER</div>
                <h1>Let's make something<br /><em>make sense.</em></h1>
                <p className="welcome-copy">Think through problems, write better code, and pick up right where you left off. Your project context stays with you.</p>
                <div className="suggestion-grid">
                  {suggestions.map((item, index) => <button className="suggestion-card" key={item.title} onClick={() => sendMessage(item.text)} disabled={busy || !activeId}><span className={`suggestion-icon suggestion-icon-${index}`}><Icon name={index === 0 ? "code" : index === 1 ? "spark" : index === 2 ? "message" : "arrow"} size={17} /></span><span><strong>{item.title}</strong><small>{item.text}</small></span><Icon name="arrow" size={15} /></button>)}
                </div>
                <div className="privacy-note"><span className="privacy-lock">*</span> Sessions and memory are stored locally; prompts go to your configured AI services.</div>
              </div>
            )}

            {hasMessages && <div className="message-list">{messages.map((message, index) => <Message key={`${index}-${message.role}`} message={message} />)}
              {busy && <div className="message-row message-assistant"><div className="assistant-avatar"><Icon name="code" size={16} /></div><div className="thinking-bubble"><span /><span /><span /></div></div>}
              {memoryOutput && <div className="memory-update-wrap"><MemoryUpdate output={memoryOutput} /></div>}
              {status?.summarizer_only && <div className="mode-note"><Icon name="spark" size={15} /> Summariser-only mode is active. Set <code>SUMMARIZER_ONLY=false</code> in <code>.env</code> to enable coding responses.</div>}
              <div ref={bottomRef} />
            </div>}
            {error && <div className="error-banner"><span>!</span>{error}<button onClick={() => setError("")} aria-label="Dismiss error">x</button></div>}
          </div>
        </section>

        <footer className="composer-area">
          <form className="composer" onSubmit={(event) => { event.preventDefault(); sendMessage(); }}>
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
                event.target.style.height = "auto";
                event.target.style.height = `${Math.min(event.target.scrollHeight, 180)}px`;
              }}
              onKeyDown={onComposerKeyDown}
              placeholder={status?.summarizer_only ? "Share a project detail to remember..." : "Ask anything about code..."}
              rows={1}
              disabled={loading || busy || !activeId}
              aria-label="Message the coding assistant"
            />
            <div className="composer-tools"><span className="composer-hint"><Icon name="spark" size={14} /> Memory-aware responses <i>&middot;</i> <kbd>Enter</kbd> to send</span><button type="submit" className="send-button" disabled={!draft.trim() || busy || loading || invalidCustomDays}><Icon name="send" size={17} /></button></div>
          </form>
          <p className="disclaimer">Recall can make mistakes. Review generated code before using it.</p>
        </footer>
      </main>
    </div>
  );
}
