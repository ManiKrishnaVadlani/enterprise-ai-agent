import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { ArrowRight, Command, Fingerprint, KeyRound, ShieldCheck } from "lucide-react";
import { useSession } from "../context/SessionContext";
import { api, ApiError } from "../services/api";
import { Button, Notice } from "../components/ui";

export function LoginPage() {
  const { authenticated, saveToken } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (authenticated) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      await api.verifyToken(token.trim());
      saveToken(token.trim());
      navigate((location.state as { from?: string } | null)?.from || "/", { replace: true });
    } catch (cause) {
      setToken("");
      setError(cause instanceof ApiError && cause.status === 401 ? "That token was not accepted. Check it and try again." : cause instanceof Error ? cause.message : "Could not verify token.");
    } finally { setBusy(false); }
  }

  return <main className="login-screen">
    <div className="login-decoration login-decoration-one" /><div className="login-decoration login-decoration-two" />
    <section className="login-card">
      <div className="login-brand"><span className="brand-mark"><Command size={20} /></span><div><b>Knowledge Agent</b><small>ENTERPRISE AI</small></div></div>
      <div className="login-icon"><Fingerprint size={24} /></div>
      <div className="eyebrow">SECURE WORKSPACE ACCESS</div><h1>Welcome back</h1>
      <p className="login-description">Connect to your private knowledge workspace using an administrator-issued API token.</p>
      <form onSubmit={submit} className="login-form">
        <label htmlFor="api-token">Bearer API token</label>
        <div className="input-with-icon"><KeyRound size={17} /><input id="api-token" type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="Paste your access token" autoComplete="current-password" required /></div>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" disabled={busy || !token.trim()} className="login-submit">{busy ? "Verifying access…" : <>Continue securely <ArrowRight size={17} /></>}</Button>
      </form>
      <div className="login-security"><ShieldCheck size={16} /><span>Your token stays in this browser session and is never included in URLs.</span></div>
      <div className="login-help">Tokens are provisioned by an administrator with <code>python -m app.provisioning create-user</code>.</div>
    </section>
    <footer className="login-footer">Enterprise AI Knowledge &amp; Workflow Agent <span>•</span> Private document intelligence</footer>
  </main>;
}
