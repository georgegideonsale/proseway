import { useEffect, useState } from "react";

export function navigate(path: string, replace = false) {
  if (path === location.pathname + location.search) return;
  if (replace) history.replaceState(null, "", path);
  else history.pushState(null, "", path);
  window.dispatchEvent(new Event("proseway:navigate"));
}

export function usePath(): string {
  const [path, setPath] = useState(location.pathname);
  useEffect(() => {
    const update = () => setPath(location.pathname);
    window.addEventListener("popstate", update);
    window.addEventListener("proseway:navigate", update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener("proseway:navigate", update);
    };
  }, []);
  return path;
}
