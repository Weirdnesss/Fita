import { useEffect, useState } from "react";

let deferredPrompt = null;
const listeners = new Set();

function notify() {
  listeners.forEach((fn) => fn());
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // stop the browser's own mini-infobar
    deferredPrompt = e;
    notify();
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    notify();
  });
}

function isStandalone() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true // iOS
  );
}

function isIos() {
  const ua = window.navigator.userAgent;
  // iPadOS reports itself as a Mac, so check for touch support too
  return /iphone|ipad|ipod/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export function usePwaInstall() {
  const [, rerender] = useState(0);

  useEffect(() => {
    const fn = () => rerender((n) => n + 1);
    listeners.add(fn);
    return () => listeners.delete(fn);
  }, []);

  const installed = isStandalone();
  const canPrompt = !!deferredPrompt && !installed;
  const showIosHelp = isIos() && !installed;

  async function install() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null; // the event can only be used once
    notify();
  }

  return { installed, canPrompt, showIosHelp, install };
}