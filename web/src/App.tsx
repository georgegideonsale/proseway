import { useEffect, useState } from "react";
import { api } from "./api";
import { Library } from "./components/Library";
import { Pair } from "./components/Pair";
import { Reader } from "./components/Reader";
import { usePath } from "./lib/router";
import { ToastProvider } from "./lib/toast";

export interface Session {
  listener: "local" | "lan";
  paired: boolean;
  ocrAvailable: boolean;
}

export function App() {
  const path = usePath();
  const [session, setSession] = useState<Session | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api
      .session()
      .then(async (s) => {
        let ocrAvailable = false;
        if (s.paired) {
          try {
            ocrAvailable = (await api.info()).ocrAvailable;
          } catch {
            /* ignore */
          }
        }
        setSession({ ...s, ocrAvailable });
      })
      .catch(() => setFailed(true));
  }, [path]);

  if (failed) {
    return (
      <main className="center-message">
        <h1>Proseway isn't reachable</h1>
        <p>Make sure it's still running on your computer, then reload this page.</p>
        <button className="btn btn-primary" onClick={() => location.reload()}>
          Reload
        </button>
      </main>
    );
  }
  if (!session) return <div className="boot" aria-busy="true" />;

  let page;
  if (session.listener === "lan" && !session.paired) {
    page = <Pair onPaired={() => setSession({ ...session, paired: true })} />;
  } else {
    const m = path.match(/^\/book\/([0-9a-f]{32})/);
    page = m ? <Reader key={m[1]} bookId={m[1]} session={session} /> : <Library session={session} />;
  }
  return <ToastProvider>{page}</ToastProvider>;
}
