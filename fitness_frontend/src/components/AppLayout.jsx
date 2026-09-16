import { Outlet } from "react-router-dom";

import BottomNav from "./BottomNav";
import { InstallBanner, OfflineBanner } from "./Status";
import useInstallPrompt from "../hooks/useInstallPrompt";
import useOnlineStatus from "../hooks/useOnlineStatus";
import Sidebar from "./Sidebar";

export default function AppLayout() {
  const isOnline = useOnlineStatus();
  const { canInstall, isIosManualInstall, promptInstall } = useInstallPrompt();

  return (
    <div className="app-layout">
      <Sidebar />

      <div className="app-main">
        {!isOnline && (
          <div className="offline-banner-wrapper">
            <OfflineBanner />
          </div>
        )}

        {isOnline && (
          <div className="offline-banner-wrapper">
            <InstallBanner
              canInstall={canInstall}
              isIosManualInstall={isIosManualInstall}
              onInstall={promptInstall}
            />
          </div>
        )}

        <main className="app-content">
          <Outlet />
        </main>
      </div>

      <BottomNav />
    </div>
  );
}
