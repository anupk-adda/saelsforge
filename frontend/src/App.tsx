import { useState } from "react";
import { Login } from "./Login";
import { Main } from "./Main";
import type { User } from "./types";

export default function App() {
  const [auth, setAuth] = useState<{ token: string; user: User } | null>(null);

  if (!auth) {
    return <Login onLogin={(token, user) => setAuth({ token, user })} />;
  }
  return (
    <Main
      token={auth.token}
      user={auth.user}
      onLogout={() => setAuth(null)}
    />
  );
}
