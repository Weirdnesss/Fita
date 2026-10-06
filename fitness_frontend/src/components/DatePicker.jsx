import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const POPUP_WIDTH = 272;
const POPUP_GAP = 6;       // space between the field and the popup
const VIEWPORT_MARGIN = 8; // minimum space kept from the screen edges

// Local calendar date as YYYY-MM-DD. Never toISOString() for "today" --
// that's UTC, which reads as yesterday in the Philippines before 8 AM.
function toDateStr(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function parseDate(str) {
  if (!str) return null;
  const [y, m, d] = str.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function daysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate();
}

/**
 * Controlled date picker, styled to match the app's <input> fields.
 * value/onChange/min/max all use YYYY-MM-DD strings, same as
 * <input type="date">, so it's a drop-in swap. Out-of-range days are
 * rendered disabled and unclickable -- no native picker involved, so
 * behavior is identical on every browser/device (this replaced the
 * native picker specifically because min/max weren't enforced
 * consistently across mobile browsers).
 *
 * Three internal views: "days" (default), "months", "years" -- tapping
 * the month/year header cycles days -> months -> years, so picking a
 * birth date decades back doesn't mean clicking the month arrow
 * hundreds of times.
 *
 * The popup is rendered in a portal on document.body with fixed
 * positioning, so no parent's overflow/stacking context can clip it or
 * hide it behind other elements. Its position is computed from the
 * field's bounding box: it opens below when there's room, above when
 * there isn't, and is always clamped inside the viewport.
 */
export default function DatePicker({ label, value, onChange, min, max, placeholder = "Select date", required = false }) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("days"); // days | months | years
  const [pos, setPos] = useState(null); // { top, left, width } in viewport px
  const selected = parseDate(value);
  const minDate = parseDate(min);
  const maxDate = parseDate(max);

  const [viewYear, setViewYear] = useState((selected || maxDate || new Date()).getFullYear());
  const [viewMonth, setViewMonth] = useState((selected || maxDate || new Date()).getMonth());

  const rootRef = useRef(null);
  const buttonRef = useRef(null);
  const popupRef = useRef(null);

  function updatePosition() {
    const btn = buttonRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    const width = Math.min(POPUP_WIDTH, vw - VIEWPORT_MARGIN * 2);
    const popupHeight = popupRef.current ? popupRef.current.offsetHeight : 320;

    const spaceBelow = vh - r.bottom - POPUP_GAP - VIEWPORT_MARGIN;
    const spaceAbove = r.top - POPUP_GAP - VIEWPORT_MARGIN;
    const openUp = spaceBelow < popupHeight && spaceAbove > spaceBelow;

    let top = openUp ? r.top - POPUP_GAP - popupHeight : r.bottom + POPUP_GAP;
    top = Math.max(VIEWPORT_MARGIN, Math.min(top, vh - popupHeight - VIEWPORT_MARGIN));

    let left = Math.min(r.left, vw - width - VIEWPORT_MARGIN);
    left = Math.max(VIEWPORT_MARGIN, left);

    setPos({ top, left, width });
  }

  // Measure after render and before paint (no flash in the wrong spot).
  // Re-run when the view changes because the days/months/years grids
  // have different heights.
  useLayoutEffect(() => {
    if (!open) {
      setPos(null);
      return;
    }
    updatePosition();
  }, [open, view, viewMonth, viewYear]);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e) {
      const inField = rootRef.current && rootRef.current.contains(e.target);
      const inPopup = popupRef.current && popupRef.current.contains(e.target);
      if (!inField && !inPopup) setOpen(false);
    }
    function onEsc(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true); // capture: catches scrolling inside any container
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  function openPicker() {
    const base = selected || maxDate || new Date();
    setViewYear(base.getFullYear());
    setViewMonth(base.getMonth());
    setView("days");
    setOpen((o) => !o);
  }

  function isDayDisabled(date) {
    if (minDate && date < minDate) return true;
    if (maxDate && date > maxDate) return true;
    return false;
  }

  function isMonthDisabled(year, month) {
    if (minDate && (year < minDate.getFullYear() || (year === minDate.getFullYear() && month < minDate.getMonth()))) return true;
    if (maxDate && (year > maxDate.getFullYear() || (year === maxDate.getFullYear() && month > maxDate.getMonth()))) return true;
    return false;
  }

  function isYearDisabled(year) {
    if (minDate && year < minDate.getFullYear()) return true;
    if (maxDate && year > maxDate.getFullYear()) return true;
    return false;
  }

  function pickDay(date) {
    if (isDayDisabled(date)) return;
    onChange(toDateStr(date));
    setOpen(false);
  }

  function pickMonth(month) {
    if (isMonthDisabled(viewYear, month)) return;
    setViewMonth(month);
    setView("days");
  }

  function pickYear(year) {
    if (isYearDisabled(year)) return;
    setViewYear(year);
    setView("months");
  }

  function shiftMonth(delta) {
    let m = viewMonth + delta;
    let y = viewYear;
    if (m < 0) { m = 11; y -= 1; }
    if (m > 11) { m = 0; y += 1; }
    setViewMonth(m);
    setViewYear(y);
  }

  function shiftYear(delta) {
    setViewYear((y) => y + delta);
  }

  function shiftYearDecade(delta) {
    setViewYear((y) => y + delta * 12);
  }

  const prevMonthDisabled = minDate && viewYear === minDate.getFullYear() && viewMonth === minDate.getMonth();
  const nextMonthDisabled = maxDate && viewYear === maxDate.getFullYear() && viewMonth === maxDate.getMonth();
  const prevYearDisabled = minDate && viewYear <= minDate.getFullYear();
  const nextYearDisabled = maxDate && viewYear >= maxDate.getFullYear();

  const firstWeekday = new Date(viewYear, viewMonth, 1).getDay();
  const totalDays = daysInMonth(viewYear, viewMonth);
  const dayCells = [];
  for (let i = 0; i < firstWeekday; i++) dayCells.push(null);
  for (let d = 1; d <= totalDays; d++) dayCells.push(d);

  const todayVal = toDateStr(new Date());
  const years = Array.from({ length: 12 }, (_, i) => viewYear - 5 + i);

  const popup = open ? (
    <div
      ref={popupRef}
      role="dialog"
      style={{
        position: "fixed",
        zIndex: 1000,
        top: pos ? pos.top : 0,
        left: pos ? pos.left : 0,
        width: pos ? pos.width : POPUP_WIDTH,
        visibility: pos ? "visible" : "hidden", // hidden until measured
        maxHeight: `calc(100vh - ${VIEWPORT_MARGIN * 2}px)`,
        overflowY: "auto",
        background: "var(--bg-card)",
        border: "1px solid var(--border-soft)",
        borderRadius: "var(--radius-md)",
        boxShadow: "0 12px 32px rgba(0,0,0,0.45)",
        padding: 12,
      }}
    >
      {view === "days" && (
        <>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <NavBtn onClick={() => shiftMonth(-1)} disabled={prevMonthDisabled} label="Previous month">‹</NavBtn>
            <HeaderBtn onClick={() => setView("months")}>
              {MONTHS[viewMonth]} {viewYear}
            </HeaderBtn>
            <NavBtn onClick={() => shiftMonth(1)} disabled={nextMonthDisabled} label="Next month">›</NavBtn>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, marginBottom: 2 }}>
            {WEEKDAYS.map((w, i) => (
              <div key={i} className="eyebrow" style={{ textAlign: "center", padding: "4px 0" }}>
                {w}
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
            {dayCells.map((d, i) => {
              if (d === null) return <div key={i} />;
              const date = new Date(viewYear, viewMonth, d);
              const dStr = toDateStr(date);
              const disabled = isDayDisabled(date);
              const isSelected = dStr === value;
              const isToday = dStr === todayVal;
              return (
                <button
                  key={i}
                  type="button"
                  disabled={disabled}
                  onClick={() => pickDay(date)}
                  className="stat"
                  style={{
                    aspectRatio: "1",
                    border: isToday && !isSelected ? "1px solid var(--chili)" : "1px solid transparent",
                    borderRadius: "var(--radius-sm)",
                    background: isSelected ? "var(--chili)" : "transparent",
                    color: disabled ? "var(--text-faint)" : isSelected ? "#fff" : "var(--text)",
                    opacity: disabled ? 0.4 : 1,
                    fontSize: 13,
                    fontWeight: isSelected ? 700 : 500,
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                >
                  {d}
                </button>
              );
            })}
          </div>
        </>
      )}

      {view === "months" && (
        <>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <NavBtn onClick={() => shiftYear(-1)} disabled={prevYearDisabled} label="Previous year">‹</NavBtn>
            <HeaderBtn onClick={() => setView("years")}>{viewYear}</HeaderBtn>
            <NavBtn onClick={() => shiftYear(1)} disabled={nextYearDisabled} label="Next year">›</NavBtn>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
            {MONTHS_SHORT.map((m, i) => {
              const disabled = isMonthDisabled(viewYear, i);
              const isSelected = selected && selected.getFullYear() === viewYear && selected.getMonth() === i;
              return (
                <button
                  key={m}
                  type="button"
                  disabled={disabled}
                  onClick={() => pickMonth(i)}
                  style={{
                    padding: "10px 4px",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid transparent",
                    background: isSelected ? "var(--chili)" : "var(--bg-raised)",
                    color: disabled ? "var(--text-faint)" : isSelected ? "#fff" : "var(--text)",
                    opacity: disabled ? 0.4 : 1,
                    fontSize: 13,
                    fontWeight: isSelected ? 700 : 500,
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                >
                  {m}
                </button>
              );
            })}
          </div>
        </>
      )}

      {view === "years" && (
        <>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <NavBtn onClick={() => shiftYearDecade(-1)} disabled={minDate && years[0] - 1 < minDate.getFullYear()} label="Previous years">‹</NavBtn>
            <span style={{ fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: 15 }}>
              {years[0]}–{years[years.length - 1]}
            </span>
            <NavBtn onClick={() => shiftYearDecade(1)} disabled={maxDate && years[years.length - 1] + 1 > maxDate.getFullYear()} label="Next years">›</NavBtn>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
            {years.map((y) => {
              const disabled = isYearDisabled(y);
              const isSelected = selected && selected.getFullYear() === y;
              return (
                <button
                  key={y}
                  type="button"
                  disabled={disabled}
                  onClick={() => pickYear(y)}
                  className="stat"
                  style={{
                    padding: "10px 4px",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid transparent",
                    background: isSelected ? "var(--chili)" : "var(--bg-raised)",
                    color: disabled ? "var(--text-faint)" : isSelected ? "#fff" : "var(--text)",
                    opacity: disabled ? 0.4 : 1,
                    fontSize: 13,
                    fontWeight: isSelected ? 700 : 500,
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                >
                  {y}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  ) : null;

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      {label && <label>{label}</label>}
      <button
        ref={buttonRef}
        type="button"
        onClick={openPicker}
        aria-haspopup="dialog"
        aria-expanded={open}
        required={required}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          textAlign: "left",
          font: "inherit",
          fontSize: 15,
          lineHeight: "normal",
          whiteSpace: "nowrap",
          color: value ? "var(--text)" : "var(--text-faint)",
          background: "var(--bg-raised)",
          border: `1px solid ${open ? "var(--chili)" : "var(--border)"}`,
          borderRadius: "var(--radius-sm)",
          padding: "11px 13px",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
          {value ? formatLabel(selected) : placeholder}
        </span>
        <CalendarIcon />
      </button>

      {popup && createPortal(popup, document.body)}
    </div>
  );
}

// Header label doubles as a button to drill into months/years -- styled
// as a visible pill with a dropdown chevron so it reads as tappable
// rather than a plain heading.
function HeaderBtn({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 5,
        background: "var(--bg-raised)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        padding: "5px 10px",
        fontFamily: "var(--font-heading)",
        fontWeight: 700,
        fontSize: 14,
        color: "var(--text)",
        cursor: "pointer",
      }}
    >
      {children}
      <ChevronDown />
    </button>
  );
}

function NavBtn({ onClick, disabled, label, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      style={{
        background: "var(--bg-raised)",
        border: "1px solid var(--border-soft)",
        borderRadius: "var(--radius-sm)",
        width: 28,
        height: 28,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 18,
        lineHeight: 1,
        padding: 0,
        color: "var(--text)",
        opacity: disabled ? 0.3 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      {children}
    </button>
  );
}

function formatLabel(date) {
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

function CalendarIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
      <rect x="3" y="4" width="18" height="18" rx="2" stroke="var(--text-faint)" strokeWidth="2" />
      <line x1="3" y1="9" x2="21" y2="9" stroke="var(--text-faint)" strokeWidth="2" />
      <line x1="8" y1="2" x2="8" y2="6" stroke="var(--text-faint)" strokeWidth="2" strokeLinecap="round" />
      <line x1="16" y1="2" x2="16" y2="6" stroke="var(--text-faint)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function ChevronDown() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
      <path d="M6 9l6 6 6-6" stroke="var(--text-faint)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}