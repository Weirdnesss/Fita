export default function StickyBar({ children, style }) {
  return (
    <div
      style={{
        position: "sticky",
        top: "var(--page-header-h, 0px)",
        zIndex: 9,
        background: "var(--bg)",
        paddingBottom: 6,
        ...style,
      }}
    >
      {children}
    </div>
  );
}