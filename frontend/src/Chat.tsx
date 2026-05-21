import { useState, useRef, useEffect } from "react";
import type { Message, User } from "./types";

const PROMPT_CHIPS = [
  "Find John Smith and show me his profile and billing information",
  "Update John Smith's address to 123 Main St, New York",
  "Change John Smith's credit card on file",
  "Change John Smith's credit card on file to Visa ending in 4321",
];

interface Props {
  user: User;
  messages: Message[];
  loading: boolean;
  onSend: (text: string) => void;
  pendingApproval?: { approvalId: string; tool: string } | null;
}

function borderColor(msg: Message): string {
  if (!msg.blocked && msg.decision !== "deny" && msg.decision !== "step_up")
    return "#2e3150";
  if (msg.decision === "deny")    return "#e74c3c";
  if (msg.decision === "step_up") return "#ffd93d";
  return "#2e3150";
}

export function Chat({ user, messages, loading, onSend, pendingApproval }: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const showChips = messages.length === 0;

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); },
            [messages]);

  function send(text: string) {
    if (!text.trim() || loading) return;
    onSend(text.trim());
    setInput("");
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "1rem" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", marginBottom: "0.8rem" }}>
        <div style={{ fontSize: "0.7rem", color: "#8b90b2",
                      textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Chat
        </div>
        <div style={{ fontSize: "0.7rem", color: "#4ecdc4",
                      background: "#0f2a2a", border: "1px solid #4ecdc4",
                      borderRadius: 12, padding: "0.2rem 0.6rem" }}>
          {user.name} · {user.role}
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", display: "flex",
                    flexDirection: "column", gap: "0.6rem" }}>
        {showChips && (
          <div style={{ background: "#13162a", border: "1px solid #2e3150",
                        borderRadius: 10, padding: "1rem" }}>
            <div style={{ fontSize: "0.82rem", color: "#e2e4f0", marginBottom: "0.8rem" }}>
              Hi {user.name}! I can help you look up and manage customer records.
              Try one of these:
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {PROMPT_CHIPS.map(chip => (
                <button key={chip} onClick={() => send(chip)}
                  style={{
                    textAlign: "left", padding: "0.5rem 0.8rem",
                    background: "#1a1d27", border: "1px solid #2e3150",
                    borderRadius: 8, color: "#6c8aff", fontSize: "0.8rem",
                    cursor: "pointer", transition: "border-color 0.15s",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = "#6c8aff")}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = "#2e3150")}
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id}
            style={{
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "85%",
              background: msg.role === "user" ? "#1a1d27" : "#0f1a2a",
              border: `1px solid ${borderColor(msg)}`,
              borderLeftWidth: msg.role === "assistant" ? 3 : 1,
              borderRadius: 8, padding: "0.6rem 0.8rem",
              fontSize: "0.82rem", lineHeight: 1.5,
            }}>
            <div style={{ fontSize: "0.68rem", color: "#8b90b2", marginBottom: 3 }}>
              {msg.role === "user" ? user.name : (
                msg.decision === "deny"    ? "⊘ Blocked by AgentTrust" :
                msg.decision === "step_up" ? "⏸ Awaiting Approval"   :
                "✓ SalesForge"
              )}
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
            {msg.decision === "step_up" && pendingApproval && (
              <div style={{ marginTop: "0.5rem", fontSize: "0.7rem",
                            color: "#ffd93d", borderTop: "1px solid #ffd93d33",
                            paddingTop: "0.4rem" }}>
                <div>Approval ID: <code style={{ fontFamily: "monospace" }}>{pendingApproval.approvalId}</code></div>
                <div style={{ marginTop: "0.3rem", opacity: 0.8 }}>
                  Approve in AgentTrust Admin → Approvals to continue…
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && !pendingApproval && (
          <div style={{ alignSelf: "flex-start", color: "#8b90b2", fontSize: "0.8rem",
                        fontStyle: "italic" }}>
            Agent is working…
          </div>
        )}
        {pendingApproval && (
          <div style={{ alignSelf: "flex-start", fontSize: "0.78rem",
                        color: "#ffd93d", fontStyle: "italic" }}>
            Waiting for admin approval in AgentTrust…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.8rem" }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send(input)}
          placeholder="Type a message…"
          style={{
            flex: 1, background: "#1a1d27", border: "1px solid #2e3150",
            borderRadius: 8, padding: "0.5rem 0.8rem", color: "#e2e4f0",
            fontSize: "0.85rem", outline: "none",
          }}
        />
        <button onClick={() => send(input)} disabled={loading}
          style={{
            padding: "0.5rem 1rem", borderRadius: 8,
            background: loading ? "#2e3150" : "#6c8aff",
            color: "#fff", border: "none", cursor: loading ? "default" : "pointer",
            fontSize: "0.85rem", fontWeight: 600,
          }}>
          Send
        </button>
      </div>
    </div>
  );
}
