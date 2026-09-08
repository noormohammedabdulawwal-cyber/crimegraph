import { useState } from "react";
import { useAuth } from "../api/AuthContext";
import { AxiosError } from "axios";

/**
 * Login screen (FR9). Exchanges username/password for a bearer token via
 * /auth/login; the token is held in the AuthContext and stamped on every
 * subsequent request by the axios interceptor. The app shows this gate
 * whenever there is no token (initial load) or after a 401 bounce.
 */
export function Login() {
  const { login, sessionExpired } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      const status = (err as AxiosError).response?.status;
      if (status === 401) setError("Incorrect username or password");
      else if (status === 503) setError("Database unavailable — is Postgres running?");
      else setError("Login failed — is the backend running on :8011?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <form
        onSubmit={handleSubmit}
        className="bg-white p-8 rounded-lg shadow-md w-full max-w-sm space-y-4"
      >
        <div>
          <h1 className="text-2xl font-bold">CrimeGraph</h1>
          <p className="text-slate-500 text-sm">
            Investigator Dashboard — sign in to continue
          </p>
        </div>
        <input
          className="w-full border rounded px-3 py-2"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
        />
        {sessionExpired && (
          <p className="text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 text-sm">
            Your session expired — please sign in again.
          </p>
        )}
        <input
          className="w-full border rounded px-3 py-2"
          placeholder="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full bg-indigo-600 text-white rounded px-3 py-2 font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="text-xs text-slate-400">
          Demo users: <code>admin</code> / <code>admin123</code> (admin) or{" "}
          <code>investigator</code> / <code>invest123</code> (read-only)
        </p>
        <p className="text-xs text-slate-400">
          Tokens are held in memory for this demo — refreshing the page returns
          here. Run <code>python backend/demo_reset.py</code> to reset demo state.
        </p>
      </form>
    </div>
  );
}
