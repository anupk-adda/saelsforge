import type { NodeStatus, SseEvent } from "./types";

interface NodeDef {
  id: keyof NodeStatus;
  label: string;
  sublabel: string;
  icon: string;
  x: number;
  y: number;
}

const NODES: NodeDef[] = [
  { id: "chatUi",        label: "Chat UI",             sublabel: "React",     icon: "💬", x: 40,  y: 180 },
  { id: "agent",         label: "LangGraph Agent",     sublabel: "Python",    icon: "🤖", x: 220, y: 180 },
  { id: "governedClient",label: "GovernedMCPClient",   sublabel: "Python",    icon: "🔌", x: 420, y: 180 },
  { id: "agentTrust",    label: "AgentTrust",          sublabel: "Go",        icon: "🛡",  x: 620, y: 90  },
  { id: "crmMcp",        label: "CRM MCP Server",      sublabel: "fastmcp",   icon: "⚡", x: 820, y: 180 },
  { id: "sqlite",        label: "SQLite CRM DB",       sublabel: "Database",  icon: "🗄", x: 1020, y: 180 },
];

const EDGES: [keyof NodeStatus, keyof NodeStatus][] = [
  ["chatUi", "agent"],
  ["agent", "governedClient"],
  ["governedClient", "agentTrust"],
  ["agentTrust", "governedClient"],   // return path
  ["governedClient", "crmMcp"],
  ["crmMcp", "sqlite"],
];

const STATE_COLORS: Record<string, string> = {
  idle:    "#2e3150",
  active:  "#6c8aff",
  allow:   "#2ecc71",
  deny:    "#e74c3c",
  step_up: "#ffd93d",
};

const NODE_W = 140, NODE_H = 70;

function nodeColor(state: string): string {
  return STATE_COLORS[state] ?? STATE_COLORS.idle;
}

function midpoint(x1: number, y1: number, x2: number, y2: number) {
  return [(x1 + x2) / 2, (y1 + y2) / 2];
}

interface Props {
  nodeStatus: NodeStatus;
  events: SseEvent[];
  riskScore: number;
  policyLabel?: string;
}

export function NodeCanvas({ nodeStatus, events, riskScore, policyLabel }: Props) {
  const canvasW = 1200, canvasH = 320;

  function getNodeCenter(id: keyof NodeStatus) {
    const n = NODES.find(n => n.id === id)!;
    return [n.x + NODE_W / 2, n.y + NODE_H / 2];
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column",
                  background: "#0d0f1a", padding: "1rem" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", marginBottom: "0.6rem" }}>
        <div style={{ fontSize: "0.7rem", color: "#8b90b2",
                      textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Agent Flow
        </div>
        {/* Risk gauge */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.7rem", color: "#8b90b2" }}>Risk</span>
          <div style={{ position: "relative", width: 120, height: 8,
                        background: "#2e3150", borderRadius: 4 }}>
            <div style={{
              width: `${Math.min(riskScore * 100, 100)}%`,
              height: "100%", borderRadius: 4, transition: "width 0.4s",
              background: riskScore > 0.85 ? "#e74c3c" :
                          riskScore > 0.5  ? "#ffd93d" : "#2ecc71",
            }} />
            {/* Threshold marker */}
            <div style={{ position: "absolute", top: -3, left: "85%",
                          width: 2, height: 14, background: "#e74c3c",
                          borderRadius: 1 }} />
          </div>
          <span style={{
            fontSize: "0.72rem", fontWeight: 600, minWidth: 32,
            color: riskScore > 0.85 ? "#e74c3c" :
                   riskScore > 0.5  ? "#ffd93d" : "#2ecc71",
          }}>
            {riskScore.toFixed(2)}
          </span>
        </div>
      </div>

      {/* SVG Canvas */}
      <div style={{ flex: 1, overflowX: "auto" }}>
        <svg viewBox={`0 0 ${canvasW} ${canvasH}`}
             style={{ width: "100%", minWidth: canvasW, height: canvasH - 40 }}>
          {/* Edges */}
          {EDGES.map(([from, to]) => {
            const [x1, y1] = getNodeCenter(from);
            const [x2, y2] = getNodeCenter(to);
            const [mx] = midpoint(x1, y1, x2, y2);
            const d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
            const fromState = nodeStatus[from];
            const toState   = nodeStatus[to];
            const active = fromState !== "idle" || toState !== "idle";
            return (
              <path key={`${from}-${to}`} d={d}
                    fill="none"
                    strokeWidth={active ? 2 : 1.5}
                    stroke={active ? nodeColor(fromState) : "#2e3150"}
                    strokeDasharray={active ? "none" : "4 4"}
                    style={{ transition: "stroke 0.3s" }} />
            );
          })}

          {/* Nodes */}
          {NODES.map(node => {
            const state = nodeStatus[node.id];
            const color = nodeColor(state);
            return (
              <g key={node.id}>
                <rect x={node.x} y={node.y} width={NODE_W} height={NODE_H} rx={8}
                      fill={state !== "idle" ? `${color}18` : "#13162a"}
                      stroke={color}
                      strokeWidth={state !== "idle" ? 2 : 1}
                      style={{ transition: "all 0.3s" }} />
                <text x={node.x + 12} y={node.y + 22}
                      fontSize={16} fill={color}>{node.icon}</text>
                <text x={node.x + 35} y={node.y + 22}
                      fontSize={11} fontWeight={600} fill={color}
                      style={{ transition: "fill 0.3s" }}>
                  {node.label}
                </text>
                <text x={node.x + 35} y={node.y + 38}
                      fontSize={9} fill="#8b90b2">
                  {node.id === "agentTrust" && policyLabel
                    ? `${policyLabel} ●`
                    : node.sublabel}
                </text>
                {/* State badge */}
                {state !== "idle" && (
                  <text x={node.x + NODE_W / 2} y={node.y + NODE_H - 8}
                        fontSize={9} fill={color} textAnchor="middle"
                        fontWeight={600}>
                    {state.toUpperCase()}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Event log strip */}
      <div style={{ display: "flex", gap: "0.4rem", overflowX: "auto",
                    paddingTop: "0.5rem", borderTop: "1px solid #2e3150",
                    minHeight: 36 }}>
        {events.slice(-8).map((e, i) => {
          const color = e.decision === "deny"    ? "#e74c3c" :
                        e.decision === "step_up" ? "#ffd93d" :
                        e.decision === "allow"   ? "#2ecc71" : "#6c8aff";
          return (
            <div key={i} style={{
              flexShrink: 0, fontSize: "0.65rem", padding: "0.2rem 0.5rem",
              borderRadius: 12, border: `1px solid ${color}`,
              color, background: `${color}18`, whiteSpace: "nowrap",
            }}>
              {e.type === "governance_check"
                ? `${e.tool} → ${e.decision} (${e.risk_score?.toFixed(2)})`
                : e.type === "tool_result"
                ? `${e.tool} ✓`
                : e.type === "agent_response"
                ? "response"
                : e.type}
            </div>
          );
        })}
      </div>
    </div>
  );
}
