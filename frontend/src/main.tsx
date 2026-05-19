import { useState, useCallback, useEffect } from "react";
import { Chat } from "./Chat";
import { NodeCanvas } from "./NodeCanvas";
import { sendChat, openStream, fetchActivePolicy } from "./api";
import type { Message, NodeStatus, SseEvent, User } from "./types";

const IDLE_STATUS: NodeStatus = {
  chatUi: "idle", agent: "idle", governedClient: "idle",
  agentTrust: "idle", crmMcp: "idle", sqlite: "idle",
};

interface Props {
  token: string;
  user: User;
  onLogout: () => void;
}

export function Main({ token, user, onLogout }: Props) {
  const [messages, setMessages]         = useState<Message[]>([]);
  const [loading,  setLoading]          = useState(false);
  const [nodeStatus, setNodeStatus]     = useState<NodeStatus>(IDLE_STATUS);
  const [events, setEvents]             = useState<SseEvent[]>([]);
  const [riskScore, setRiskScore]       = useState(0);
  const [policyLabel, setPolicyLabel]   = useState<string>("…");

  useEffect(() => {
    fetchActivePolicy().then(p => setPolicyLabel(p.label));
  }, []);

  const addMessage = useCallback((msg: Omit<Message, "id">) => {
    setMessages(prev => [...prev, { ...msg, id: crypto.randomUUID() }]);
  }, []);

  function applyEvent(e: SseEvent) {
    setEvents(prev => [...prev, e]);

    if (e.type === "agent_start") {
      setNodeStatus({ ...IDLE_STATUS, chatUi: "active", agent: "active" });
    }
    if (e.type === "governance_request") {
      setNodeStatus(s => ({ ...s, governedClient: "active", agentTrust: "active" }));
    }
    if (e.type === "governance_check") {
      const d = e.decision!;
      if (e.risk_score !== undefined) setRiskScore(e.risk_score);
      setNodeStatus(s => ({
        ...s,
        agentTrust: d,
        crmMcp:     d === "allow" ? "active" : "idle",
        sqlite:     d === "allow" ? "active" : "idle",
        governedClient: d,
      }));
    }
    if (e.type === "tool_result") {
      setNodeStatus(s => ({ ...s, crmMcp: "allow", sqlite: "allow" }));
    }
    if (e.type === "agent_response") {
      setNodeStatus(s => ({ ...s, chatUi: "allow", agent: "allow" }));
    }
    if (e.type === "done") {
      setTimeout(() => setNodeStatus(IDLE_STATUS), 2000);
    }
  }

  async function handleSend(text: string) {
    setLoading(true);
    setEvents([]);
    setRiskScore(0);
    addMessage({ role: "user", content: text });

    try {
      const { session_id, response } = await sendChat(text, token);

      // Open SSE stream for canvas animation
      const close = openStream(session_id, applyEvent);

      // The response is already available synchronously from /chat
      // SSE stream catches up with events emitted during the run
      const lastEvent = events[events.length - 1];
      addMessage({
        role: "assistant",
        content: response,
        decision: lastEvent?.decision,
        blocked: lastEvent?.decision === "deny" || lastEvent?.decision === "step_up",
      });

      setTimeout(close, 3000);  // close stream after events drain
    } catch (err) {
      addMessage({ role: "assistant", content: `Error: ${err}`, blocked: true });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column",
                  background: "#0d0f1a" }}>
      {/* Top bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "0.5rem 1rem", borderBottom: "1px solid #2e3150",
                    background: "#13162a" }}>
        <div style={{ fontWeight: 700, color: "#e2e4f0" }}>SalesForge</div>
        <div style={{ fontSize: "0.75rem", color: "#4ecdc4" }}>
          salesforge-agent · governed by AgentTrust
        </div>
        <button onClick={onLogout}
          style={{ background: "none", border: "1px solid #2e3150", borderRadius: 6,
                   color: "#8b90b2", fontSize: "0.75rem", padding: "0.3rem 0.7rem",
                   cursor: "pointer" }}>
          Switch User
        </button>
      </div>

      {/* Split layout */}
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr",
                    overflow: "hidden", borderTop: "1px solid #2e3150" }}>
        <div style={{ borderRight: "1px solid #2e3150", overflow: "hidden" }}>
          <Chat user={user} messages={messages} loading={loading} onSend={handleSend} />
        </div>
        <div style={{ overflow: "hidden" }}>
          <NodeCanvas nodeStatus={nodeStatus} events={events} riskScore={riskScore}
                      policyLabel={policyLabel} />
        </div>
      </div>
    </div>
  );
}
