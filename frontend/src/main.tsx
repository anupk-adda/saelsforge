import { useState, useCallback, useEffect, useRef } from "react";
import { Chat } from "./Chat";
import { NodeCanvas } from "./NodeCanvas";
import { sendChat, openStream, fetchActivePolicy, checkApproval, resumeChat } from "./api";
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
  const [pendingApproval, setPendingApproval] = useState<{
    chatId: string; approvalId: string; tool: string;
  } | null>(null);
  const approvalPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (approvalPollRef.current) clearInterval(approvalPollRef.current);
    };
  }, []);

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
    if (approvalPollRef.current) {
      clearInterval(approvalPollRef.current);
      approvalPollRef.current = null;
      setPendingApproval(null);
    }
    setLoading(true);
    setEvents([]);
    setRiskScore(0);
    addMessage({ role: "user", content: text });

    try {
      const body = await sendChat(text, token);
      const { session_id, response } = body;

      // Open SSE stream for canvas animation
      const close = openStream(session_id, applyEvent);

      const lastEvent = events[events.length - 1];
      addMessage({
        role: "assistant",
        content: response,
        decision: lastEvent?.decision,
        blocked: lastEvent?.decision === "deny" || lastEvent?.decision === "step_up",
      });

      if (body.step_up_pending) {
        const { approval_id, tool } = body.step_up_pending;
        setPendingApproval({ chatId: session_id, approvalId: approval_id, tool });
        approvalPollRef.current = setInterval(async () => {
          const { status } = await checkApproval(session_id);
          if (status === "approved") {
            clearInterval(approvalPollRef.current!);
            approvalPollRef.current = null;
            setPendingApproval(null);
            setLoading(true);
            try {
              const resumed = await resumeChat(session_id);
              const closeResumed = openStream(resumed.session_id, applyEvent);
              addMessage({ role: "assistant", content: resumed.response });
              setTimeout(closeResumed, 3000);
            } catch (err) {
              addMessage({ role: "assistant", content: `Resume failed: ${err}`, blocked: true });
            } finally {
              setLoading(false);
            }
          } else if (status === "denied") {
            clearInterval(approvalPollRef.current!);
            approvalPollRef.current = null;
            setPendingApproval(null);
            addMessage({ role: "assistant", content: "Request denied by administrator.", blocked: true });
          }
        }, 3000);
      }

      setTimeout(close, 3000);
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
          <Chat user={user} messages={messages} loading={loading} onSend={handleSend}
                pendingApproval={pendingApproval
                  ? { approvalId: pendingApproval.approvalId, tool: pendingApproval.tool }
                  : null} />
        </div>
        <div style={{ overflow: "hidden" }}>
          <NodeCanvas nodeStatus={nodeStatus} events={events} riskScore={riskScore}
                      policyLabel={policyLabel} />
        </div>
      </div>
    </div>
  );
}
