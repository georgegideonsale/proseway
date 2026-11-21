import { useEffect, useRef, useState } from "react";
import { api } from "../api";

/** Shown on a phone that opened the shared address but hasn't paired yet. */
export function Pair({ onPaired }: { onPaired: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const tried = useRef(false);

  async function submit(secret: string) {
    setBusy(true);
    setError(null);
    try {
      await api.pair(secret);
      history.replaceState(null, "", "/");
      onPaired();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    // The QR code carries a one-time token in the URL fragment, which never leaves the phone
    // except in this request.
    const m = location.hash.match(/t=([A-Za-z0-9_-]{10,})/);
    if (m && !tried.current) {
      tried.current = true;
      history.replaceState(null, "", location.pathname);
      submit(m[1]);
    }
    document.title = "Pair your phone — Proseway";
  }, []);

  return (
    <main className="pair">
      <div className="wordmark" aria-label="Proseway">
        <span className="wordmark-text">Proseway</span>
        <span className="wordmark-ribbon" aria-hidden="true" />
      </div>
      <h1>Pair this phone</h1>
      <p>Enter the six-digit code shown on your computer under “Read on your phone”.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (code.length === 6) submit(code);
        }}
      >
        <label htmlFor="pair-code" className="visually-hidden">
          Pairing code
        </label>
        <input
          id="pair-code"
          className="input pair-input"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          autoFocus
        />
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="btn btn-primary btn-lg" disabled={busy || code.length !== 6}>
          {busy ? "Pairing…" : "Pair"}
        </button>
      </form>
      <p className="pair-note">Pairing keeps this phone signed in to your library on this network. You can unpair it from the computer at any time.</p>
    </main>
  );
}
