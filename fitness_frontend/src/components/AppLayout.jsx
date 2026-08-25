import { Outlet } from "react-router-dom";
import BottomNav from "./BottomNav";
import { OfflineBanner } from "./Status";
import useOnlineStatus from "../hooks/useOnlineStatus";

export default function AppLayout() {
  const isOnline = useOnlineStatus();

  return (
    <>
      {!isOnline && (
        <div style={{ padding: "10px 16px 0" }}>
          <OfflineBanner />
        </div>
      )}
      <Outlet />
      <BottomNav />
    </>
  );
}
