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

const SECURE_KEY = "proseway.share.secure";

function timeLeft(ts: number | null): string {
  if (!ts) return "";
  const mins = Math.max(0, Math.round((ts - Date.now() / 1000) / 60));
  if (mins >= 60) return `${Math.floor(mins / 60)} h ${mins % 60} min`;
  return `${mins} min`;
}

function loadSecure(): boolean {
  try {
    return localStorage.getItem(SECURE_KEY) !== "0";
  } catch {
    return true;
  }
}

function saveSecure(on: boolean) {
  try {
    localStorage.setItem(SECURE_KEY, on ? "1" : "0");
  } catch {
    /* private mode: the choice just isn't remembered */
  }
}

function Fingerprint({ value }: { value: string }) {
  // Grouped in fours so it's easy to compare with what the phone shows.
  const pairs = value.split(":");
  const groups: string[] = [];
  for (let i = 0; i < pairs.length; i += 4) groups.push(pairs.slice(i, i + 4).join(":"));
  return (
    <code className="fingerprint" aria-label={`SHA-256 fingerprint ${pairs.join(" ")}`}>
      {groups.map((g, i) => (
        <span key={i}>{g}</span>
      ))}
    </code>
  );
}

export function SharingDialog({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<SharingState | null>(null);
  const [address, setAddress] = useState("");
  const [minutes, setMinutes] = useState(120);
  const [secure, setSecure] = useState(loadSecure);
  const [showSetup, setShowSetup] = useState(false);
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
      const useSecure = on && secure && !!state?.secureAvailable;
      const s = await api.setSharing(on, address, minutes, useSecure);
      setState(s);
      setShowSetup(false);
      setQrKey((k) => k + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const setupQr = !!state?.enabled && state.secure && showSetup && !!state.setupUrl;

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
            <>
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
              {state.secureAvailable && (
                <label className="toggle share-secure">
                  <input
                    type="checkbox"
                    checked={secure}
                    aria-describedby="sh-secure-hint"
                    onChange={(e) => {
                      setSecure(e.target.checked);
                      saveSecure(e.target.checked);
                    }}
                  />
                  <span>
                    Secure connection (recommended)
                    <span id="sh-secure-hint" className="share-hint">
                      Encrypts everything between your phone and this computer, and lets your phone add Proseway to its home
                      screen and keep chapters for reading offline. Each phone has to trust Proseway's certificate once. We'll
                      show you how.
                    </span>
                  </span>
                </label>
              )}
            </>
          )}
          <p className="share-note">
            {secure && state.secureAvailable
              ? "Your computer may ask whether to allow the connection."
              : "Without a secure connection, someone else on the same network could see what you read. Only use it on a network you trust, like your home Wi-Fi. Your computer may ask whether to allow the connection."}
          </p>
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
              {setupQr ? (
                <img
                  key={`setup-${qrKey}`}
                  src={`/api/sharing/qr.svg?target=setup&k=${qrKey}`}
                  alt={`QR code that opens the certificate setup page, ${state.setupUrl}`}
                />
              ) : state.pairing && !state.locked ? (
                <img key={qrKey} src={`/api/sharing/qr.svg?k=${qrKey}`} alt={`QR code that opens ${state.url} and pairs your phone`} />
              ) : (
                <p className="qr-locked">Pairing is paused after several wrong codes.</p>
              )}
            </div>
            {setupQr ? (
              <ol className="share-steps" aria-label="Set up a secure connection">
                <li>Scan this code with your phone's camera. It opens a setup page on your Wi-Fi.</li>
                <li>Download Proseway's certificate there and trust it. The page walks you through it on iPhone and Android.</li>
                {state.ca && (
                  <li>
                    Your phone should show this fingerprint for the certificate. If it shows a different one, don't trust it.
                    <Fingerprint value={state.ca.fingerprint} />
                  </li>
                )}
                <li>
                  <button className="link-btn" onClick={() => setShowSetup(false)}>
                    Done, show the pairing code
                  </button>
                </li>
              </ol>
            ) : (
              <ol className="share-steps">
                <li>Connect your phone to the same Wi-Fi as this computer.</li>
                {state.secure && (
                  <li>
                    First time on this phone? Trust Proseway's certificate once.{" "}
                    {state.setupUrl ? (
                      <button className="link-btn" onClick={() => (setShowSetup(true), setQrKey((k) => k + 1))}>
                        Set up this phone
                      </button>
                    ) : (
                      <a className="link-btn" href="/api/sharing/ca.crt" download>
                        Download the certificate
                      </a>
                    )}
                  </li>
                )}
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
            )}
          </div>
          <p className="share-meta">
            Sharing turns off in {timeLeft(state.expiresAt)}. Codes work once and expire after five minutes.
            <button className="link-btn" onClick={() => api.newCode().then((s) => (setState(s), setQrKey((k) => k + 1)))}>
              New code
            </button>
          </p>
          {state.secure ? (
            <p className="share-note">
              Secure connection. If your phone warns about the certificate, it hasn't trusted it yet. You can also{" "}
              <a href="/api/sharing/ca.crt" download>
                download the certificate
              </a>{" "}
              and send it to your phone yourself, for example by AirDrop or a USB cable.
            </p>
          ) : (
            <p className="share-note">
              This connection isn't encrypted, so your phone can't install Proseway or read offline. Turn sharing off and
              on again to choose a secure connection.
            </p>
          )}
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
