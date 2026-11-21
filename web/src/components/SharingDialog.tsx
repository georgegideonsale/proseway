import { useEffect, useState } from "react";
import { api } from "../api";
import type { SharingState } from "../types";
import { Dialog } from "./Dialog";

const DURATIONS = [
  { minutes: 60, label: "1 hour" },
  { minutes: 120, label: "2 hours" },
  { minutes: 240, label: "4 hours" },
  { minutes: 720, label: "12 hours" },
];

function timeLeft(ts: number | null): string {
  if (!ts) return "";
  const mins = Math.max(0, Math.round((ts - Date.now() / 1000) / 60));
  if (mins >= 60) return `${Math.floor(mins / 60)} h ${mins % 60} min`;
  return `${mins} min`;
}

export function SharingDialog({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<SharingState | null>(null);
  const [address, setAddress] = useState("");
  const [minutes, setMinutes] = useState(120);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qrKey, setQrKey] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .sharing()
        .then((s) => {
          if (!alive) return;
          setState((prev) => {
            if (prev?.pairing?.code !== s.pairing?.code) setQrKey((k) => k + 1);
            return s;
          });
          setAddress((a) => a || s.address || s.addresses[0]?.address || "");
        })
        .catch((e) => alive && setError(e.message));
    load();
    const t = window.setInterval(load, 3000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);

  async function toggle(on: boolean) {
    setBusy(true);
    setError(null);
    try {
      const s = await api.setSharing(on, address, minutes);
      setState(s);
      setQrKey((k) => k + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title="Read on your phone" onClose={onClose} wide>
      {!state ? (
        <div className="spinner" aria-label="Loading" />
      ) : !state.enabled ? (
        <div className="share-off">
          <p>
            Your phone can open your library over your home Wi-Fi. Proseway only listens on this computer until you turn
            this on, and every phone has to pair with a code first.
          </p>
          {state.addresses.length === 0 ? (
            <p className="form-error">This computer doesn't seem to be connected to a local network.</p>
          ) : (
            <div className="share-options">
              {state.addresses.length > 1 && (
                <div className="field">
                  <label htmlFor="sh-addr">Network</label>
                  <select id="sh-addr" className="input" value={address} onChange={(e) => setAddress(e.target.value)}>
                    {state.addresses.map((a) => (
                      <option key={a.address} value={a.address}>
                        {a.interface} ({a.address})
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div className="field">
                <label htmlFor="sh-dur">Turn off automatically after</label>
                <select id="sh-dur" className="input" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
                  {DURATIONS.map((d) => (
                    <option key={d.minutes} value={d.minutes}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
          <p className="share-note">Only use this on a network you trust, like your home Wi-Fi. Your computer may ask whether to allow the connection.</p>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button className="btn" onClick={onClose}>
              Not now
            </button>
            <button className="btn btn-primary" disabled={busy || state.addresses.length === 0} onClick={() => toggle(true)}>
              Turn on sharing
            </button>
          </div>
        </div>
      ) : (
        <div className="share-on">
          <div className="share-grid">
            <div className="qr-frame">
              {state.pairing && !state.locked ? (
                <img key={qrKey} src={`/api/sharing/qr.svg?k=${qrKey}`} alt={`QR code that opens ${state.url} and pairs your phone`} />
              ) : (
                <p className="qr-locked">Pairing is paused after several wrong codes.</p>
              )}
            </div>
            <ol className="share-steps">
              <li>Connect your phone to the same Wi-Fi as this computer.</li>
              <li>Scan the code with your phone's camera.</li>
              <li>
                Or open <strong className="share-url">{state.url}</strong> and enter
                <span className="pair-code" aria-label={`code ${state.pairing?.code.split("").join(" ")}`}>
                  {state.pairing?.code.slice(0, 3)}
                  <span className="pair-code-gap" />
                  {state.pairing?.code.slice(3)}
                </span>
              </li>
            </ol>
          </div>
          <p className="share-meta">
            Sharing turns off in {timeLeft(state.expiresAt)}. Codes work once and expire after five minutes.
            <button className="link-btn" onClick={() => api.newCode().then((s) => (setState(s), setQrKey((k) => k + 1)))}>
              New code
            </button>
          </p>
          {state.devices.length > 0 && (
            <section className="devices" aria-label="Paired devices">
              <h3>Paired devices</h3>
              <ul>
                {state.devices.map((d) => (
                  <li key={d.id}>
                    <span>
                      {d.name}
                      <span className="device-seen">
                        {d.lastSeen ? `last used ${new Date(d.lastSeen * 1000).toLocaleString()}` : "never used"}
                      </span>
                    </span>
                    <button className="link-btn" onClick={() => api.revokeDevice(d.id).then(setState)}>
                      Unpair
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button className="btn" disabled={busy} onClick={() => toggle(false)}>
              Turn off sharing
            </button>
            <button className="btn btn-primary" onClick={onClose}>
              Done
            </button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
