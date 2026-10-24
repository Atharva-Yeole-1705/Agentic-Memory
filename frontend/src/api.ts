const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

export type Memory = { id: string; content: string; memory_type: string; source: string; created_at: string; updated_at: string; expires_at?: string | null };
export type ChatMessage = { role: "user" | "assistant"; content: string };
export type Session = { id: string; title: string; messages: ChatMessage[]; updated_at: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Request failed");
  return response.status === 204 ? undefined as T : response.json();
}

export const api = {
  sessions: () => request<Session[]>("/sessions"),
  createSession: () => request<Session>("/sessions", { method: "POST", body: JSON.stringify({}) }),
  session: (id: string) => request<Session>(`/sessions/${id}`),
  send: (id: string, content: string) => request<{ reply: string; retrieved_memories: Memory[] }>(`/sessions/${id}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
  memories: () => request<Memory[]>("/memories"),
  addMemory: (content: string) => request<Memory>("/memories", { method: "POST", body: JSON.stringify({ content, memory_type: "fact" }) }),
  deleteMemory: (id: string) => request<void>(`/memories/${id}`, { method: "DELETE" }),
};
