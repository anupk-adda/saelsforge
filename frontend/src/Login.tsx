import { useState } from "react";
import { login } from "./api";
import type { User } from "./types";

const DEMO_USERS = [
  { email: "alice@salesforge.demo",  name: "Alice",  role: "Sales Rep",     color: "#6c8aff" },
  { email: "bob@salesforge.demo",    name: "Bob",    role: "Sales Manager", color: "#4ecdc4" },
  { email: "carol@salesforge.demo",  name: "Carol",  role: "Billing Admin", color: "#ffd93d" },
  { email: "dave@salesforge.demo",   name: "Dave",   role: "Support Agent", color: "#a78bfa" },
  { email: "admin@salesforge.demo",  name: "Admin",  role: "Admin",         color: "#2ecc71" },
];

interface Props {
  onLogin: (token: string, user: User) => void;
}

export function Login({ onLogin }: Props) {
  const [selected, setSelected] = useState(DEMO_USERS[0].email);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSignIn() {
    setLoading(true);
    setError("");
    try {
      const { token, user } = await login(selected, "demo1234");
      onLogin(token, user);
    } catch {
      setError("Login failed — check credentials");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center",
                  justifyContent: "center", background: "#0d0f1a" }}>
      <div style={{ width: 380, background: "#13162a", borderRadius: 12,
                    border: "1px solid #2e3150", padding: "2rem" }}>
        <div style={{ textAlign: "center", marginBottom: "1.5rem" }}>
          <div style={{ fontSize: "1.8rem", fontWeight: 700, color: "#e2e4f0" }}>
            SalesForge
          </div>
          <div style={{ color: "#8b90b2", fontSize: "0.85rem", marginTop: 4 }}>
            CRM Assistant · Governed by AgentTrust
          </div>
        </div>

        <div style={{ marginBottom: "1.2rem" }}>
          <div style={{ fontSize: "0.75rem", color: "#8b90b2",
                        textTransform: "uppercase", letterSpacing: "0.06em",
                        marginBottom: "0.6rem" }}>
            Sign in as
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {DEMO_USERS.map(u => (
              <button
                key={u.email}
                onClick={() => setSelected(u.email)}
                style={{
                  padding: "0.4rem 0.8rem", borderRadius: 20, cursor: "pointer",
                  fontSize: "0.8rem", border: `2px solid ${selected === u.email ? u.color : "#2e3150"}`,
                  background: selected === u.email ? `${u.color}22` : "#1a1d27",
                  color: selected === u.email ? u.color : "#8b90b2",
                  transition: "all 0.15s",
                }}
              >
                {u.name}
                <span style={{ fontSize: "0.65rem", opacity: 0.7, marginLeft: 4 }}>
                  {u.role}
                </span>
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div style={{ color: "#e74c3c", fontSize: "0.8rem",
                        marginBottom: "0.8rem", textAlign: "center" }}>
            {error}
          </div>
        )}

        <button
          onClick={handleSignIn}
          disabled={loading}
          style={{
            width: "100%", padding: "0.7rem", borderRadius: 8,
            background: loading ? "#2e3150" : "#6c8aff",
            color: "#fff", fontWeight: 600, fontSize: "0.9rem",
            border: "none", cursor: loading ? "default" : "pointer",
          }}
        >
          {loading ? "Signing in…" : "Sign In"}
        </button>
      </div>
    </div>
  );
}
