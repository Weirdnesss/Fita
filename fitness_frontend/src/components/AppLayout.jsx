import { Outlet } from "react-router-dom";

import BottomNav from "./BottomNav";
import { OfflineBanner } from "./Status";
import useOnlineStatus from "../hooks/useOnlineStatus";
import Sidebar from "./Sidebar";

export default function AppLayout() {
  const isOnline = useOnlineStatus();

  return (
    <div className="app-layout">
      <Sidebar />

      <div className="app-main">
        {!isOnline && (
          <div className="offline-banner-wrapper">
            <OfflineBanner />
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
