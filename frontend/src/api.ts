import type { User, SseEvent, ChatResponse } from "./types";

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
): Promise<ChatResponse> {
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

export async function fetchActivePolicy(): Promise<{ label: string }> {
  try {
    const r = await fetch("/at-policy");
    if (r.ok) return r.json();
  } catch { /* AT unreachable */ }
  return { label: "default" };
}

export async function checkApproval(chatId: string): Promise<{ status: string }> {
  try {
    const r = await fetch(`/chat/approval/${chatId}`);
    if (r.ok) return r.json();
  } catch { /* network error */ }
  return { status: "pending" };
}

export async function resumeChat(chatId: string): Promise<ChatResponse> {
  const r = await fetch(`/chat/resume/${chatId}`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
