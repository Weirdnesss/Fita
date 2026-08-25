import { useEffect, useState } from "react";

/**
 * Tracks navigator.onLine, updated live via the browser's online/offline
 * events. Note this only reflects network *connectivity*, not whether the
 * API host specifically is reachable -- a captive portal or a down backend
 * can still show "online".
 */
export default function useOnlineStatus() {
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  return isOnline;
}
