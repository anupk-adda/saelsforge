import type { User, SseEvent } from "./types";

const BASE = "";  // proxied by Vite dev server

export async function login(email: string, password: string): Promise<{ token: string; user: User }> {
  const r = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error("Invalid credentials");
  return r.json();
}

export async function sendChat(
  message: string,
  token: string
): Promise<{ session_id: string; at_session_id: string; response: string }> {
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function openStream(
  sessionId: string,
  onEvent: (e: SseEvent) => void
): () => void {
  const es = new EventSource(`${BASE}/stream/${sessionId}`);
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as SseEvent);
    } catch { /* ignore parse errors */ }
  };
  return () => es.close();
}
