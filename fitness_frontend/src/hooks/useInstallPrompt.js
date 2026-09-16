import { useEffect, useState } from "react";

function isStandalone() {
  // Covers Chrome/Edge/desktop ("standalone") and iOS Safari's older
  // proprietary flag -- there's no single cross-browser API for this.
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

function isIos() {
  return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}

/**
 * Drives an "Install app" prompt.
 *
 * Chrome/Edge/Android fire `beforeinstallprompt`, which we capture and
 * replay later via `promptInstall()`. Safari (iOS/iPadOS) never fires that
 * event -- there's no programmatic install there, only the manual
 * Share -> Add to Home Screen flow -- so `isIosManualInstall` tells the
 * caller to show instructions instead of a button.
 */
export default function useInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [installed, setInstalled] = useState(isStandalone());

  useEffect(() => {
    const onBeforeInstallPrompt = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    const onAppInstalled = () => {
      setInstalled(true);
      setDeferredPrompt(null);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onAppInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onAppInstalled);
    };
  }, []);

  async function promptInstall() {
    if (!deferredPrompt) return null;
    deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    // The captured event can only be used once, win or lose.
    setDeferredPrompt(null);
    return choice.outcome; // "accepted" | "dismissed"
  }

  return {
    canInstall: !installed && !!deferredPrompt,
    isIosManualInstall: !installed && isIos() && !deferredPrompt,
    installed,
    promptInstall,
  };
}
