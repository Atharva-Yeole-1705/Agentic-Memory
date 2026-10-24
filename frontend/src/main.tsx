import { FormEvent, useEffect, useState } from "react";
import { api, Memory, Session } from "./api";
import "./styles.css";
import "./retrieval.css";

function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [active, setActive] = useState<Session | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [retrievedIds, setRetrievedIds] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [memoryText, setMemoryText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = async () => {
    try { const [nextSessions, nextMemories] = await Promise.all([api.sessions(), api.memories()]); setSessions(nextSessions); setMemories(nextMemories); if (!active && nextSessions[0]) setActive(nextSessions[0]); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not connect to the API"); }
  };
  useEffect(() => { void refresh(); }, []);
  const newSession = async () => { const session = await api.createSession(); setSessions([session, ...sessions]); setActive(session); };
  const openSession = async (id: string) => { setActive(await api.session(id)); };
  const send = async (event: FormEvent) => {
    event.preventDefault(); if (!active || !prompt.trim() || loading) return;
    const content = prompt.trim(); setPrompt(""); setLoading(true); setError("");
    setActive({ ...active, messages: [...active.messages, { role: "user", content }] });
    try { const result = await api.send(active.id, content); setRetrievedIds(result.retrieved_memories.map(memory => memory.id)); const next = await api.session(active.id); setActive(next); setMemories(await api.memories()); }
    catch (err) { setError(err instanceof Error ? err.message : "Message failed"); }
    finally { setLoading(false); }
  };
  const addMemory = async (event: FormEvent) => { event.preventDefault(); if (!memoryText.trim()) return; await api.addMemory(memoryText.trim()); setMemoryText(""); setMemories(await api.memories()); };
  return <main className="app-shell">
    <aside className="sidebar"><div className="brand">✦ Agentic<br />Memory</div><button className="new-button" onClick={() => void newSession()}>＋ New session</button><p className="side-label">Conversations</p>{sessions.map(s => <button key={s.id} className={`session ${active?.id === s.id ? "selected" : ""}`} onClick={() => void openSession(s.id)}>▣ {s.title}<span>›</span></button>)}</aside>
    <section className="chat"><header><div><p className="eyebrow">PERSISTENT AI ASSISTANT</p><h1>{active?.title ?? "Choose or create a session"}</h1></div><span className="status">Memory enabled</span></header>{error && <p className="error">{error}</p>}<div className="messages">{active?.messages.length ? active.messages.map((m, i) => <article key={i} className={`message ${m.role}`}><span>{m.role === "user" ? "You" : "Agent"}</span><p>{m.content}</p></article>) : <div className="empty"><b>✦</b><h2>Memory that changes the answer</h2><p>Start a conversation. Durable project facts are saved and retrieved in later sessions.</p></div>}{loading && <article className="message assistant"><span>Agent</span><p>Recalling context and thinking…</p></article>}</div><form className="composer" onSubmit={send}><input value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Ask about your project…" disabled={!active || loading} /><button aria-label="Send" disabled={!active || loading}>↑</button></form></section>
    <aside className="memory-panel"><header><p className="eyebrow">LONG-TERM CONTEXT</p><h2>Memory ledger</h2><p className="muted">{retrievedIds.length ? `${retrievedIds.length} memories retrieved for the latest answer.` : "Inspect what can influence future answers."}</p></header><form className="memory-form" onSubmit={addMemory}><input value={memoryText} onChange={e => setMemoryText(e.target.value)} placeholder="Add a durable fact" /><button>Add</button></form><div className="memory-list">{memories.map(memory => <article className={`memory ${retrievedIds.includes(memory.id) ? "retrieved" : ""}`} key={memory.id}><div><span className="tag">{memory.memory_type}</span><p>{memory.content}</p><small>{memory.source} · updated {new Date(memory.updated_at).toLocaleDateString()}</small></div><button aria-label="Delete memory" onClick={async () => { await api.deleteMemory(memory.id); setMemories(await api.memories()); }}>×</button></article>)}{!memories.length && <p className="muted">No saved memories yet.</p>}</div></aside>
  </main>;
}
export default App;
import { createRoot } from "react-dom/client";
createRoot(document.getElementById("root")!).render(<App />);
