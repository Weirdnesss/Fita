/**
 * Keeps its children on screen while the page scrolls.
 *   <Pinned>          sticks just under the page header (search bars, tabs, filters)
 *   <Pinned bottom>   sticks just above the bottom nav (Save / Add buttons)
 * It has its own background so scrolling content doesn't show through.
 */
export default function Pinned({ bottom = false, className, style, children }) {
  return (
    <div
      className={className}
      style={{
        position: "sticky",
        ...(bottom ? { bottom: "calc(var(--nav-height, 0px) + 8px)" } : { top: "var(--page-header-h, 0px)" }),
        zIndex: 9,
        background: "var(--bg)",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: bottom ? "8px 0" : "0 0 6px",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
