export interface User {
  email: string;
  role: string;
  name: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  decision?: "allow" | "deny" | "step_up";
  blocked?: boolean;
}

export type SseEventType =
  | "agent_start"
  | "governance_request"
  | "governance_check"
  | "tool_result"
  | "agent_response"
  | "done";

export interface SseEvent {
  type: SseEventType;
  tool?: string;
  decision?: "allow" | "deny" | "step_up";
  risk_score?: number;
  reason?: string;
  approval_id?: string;
  result?: unknown;
  content?: string;
  args?: Record<string, unknown>;
}

export type NodeState = "idle" | "active" | "allow" | "deny" | "step_up";

export interface NodeStatus {
  chatUi: NodeState;
  agent: NodeState;
  governedClient: NodeState;
  agentTrust: NodeState;
  crmMcp: NodeState;
  sqlite: NodeState;
}

export interface ChatResponse {
  session_id: string;
  at_session_id: string;
  response: string;
  step_up_pending?: { approval_id: string; tool: string };
}
