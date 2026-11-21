import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/literata/wght.css";
import "@fontsource-variable/literata/wght-italic.css";
import "@fontsource-variable/source-serif-4/wght.css";
import "@fontsource-variable/source-serif-4/wght-italic.css";
import "@fontsource-variable/atkinson-hyperlegible-next/wght.css";
import "@fontsource/opendyslexic/400.css";
import "@fontsource/opendyslexic/700.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/library.css";
import "./styles/reader.css";
import { App } from "./App";
import { applyPrefs, loadPrefs } from "./lib/prefs";

applyPrefs(loadPrefs());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// Offline reading needs a service worker, which browsers only allow in a secure context
// (localhost). Phones reach Proseway over plain HTTP, so they don't get offline caching yet.
if ("serviceWorker" in navigator && window.isSecureContext && import.meta.env.PROD) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
