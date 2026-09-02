/**
 * Controlled confirmation modal, matching the app's dark theme -- unlike
 * window.confirm(), which renders as an unstyled native browser dialog
 * that looks out of place in an installed PWA.
 *
 * Usage: render unconditionally with `open` controlling visibility, so
 * it can transition in/out; returns null when closed.
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}) {
  if (!open) return null;

  return (
    <div
      onClick={onCancel}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        zIndex: 1000,
      }}
    >
      <div
        className="card"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 340 }}
      >
        {title && <p style={{ fontWeight: 600, marginBottom: 6 }}>{title}</p>}
        <p style={{ fontSize: 14, color: "var(--text-dim)", marginBottom: 18 }}>{message}</p>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-secondary" style={{ flex: 1 }} onClick={onCancel}>
            {cancelLabel}
          </button>
          {/* .btn-primary is already chili-colored, which doubles as this
              app's destructive/emphasis color -- no separate "danger"
              variant needed. */}
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
