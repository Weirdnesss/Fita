import { useState } from "react";
import { cmToFtIn, ftInToCm } from "../lib/profile";
import UnitToggle from "./UnitToggle";

// Backend only stores height_ft/height_in (see accounts/models.py --
// height_cm is a derived read-only property). This component is a
// frontend-only convenience: cm mode is just a different way to edit
// the same ft/in values, converted on every keystroke.
export default function HeightField({ ft, inch, onChange, required = false }) {
  const [unit, setUnit] = useState("ftin"); // "ftin" | "cm"
  const [cmDraft, setCmDraft] = useState(() => (ft ? String(ftInToCm(ft, inch)) : ""));

  function switchUnit(next) {
    if (next === unit) return;
    if (next === "cm") {
      setCmDraft(ft ? String(ftInToCm(ft, inch)) : "");
    }
    setUnit(next);
  }

  function handleCmChange(e) {
    const raw = e.target.value;
    setCmDraft(raw);
    const cm = Number(raw);
    if (raw !== "" && !Number.isNaN(cm) && cm > 0) {
      const { ft: newFt, inch: newInch } = cmToFtIn(cm);
      onChange({ ft: newFt, inch: newInch });
    } else {
      onChange({ ft: "", inch: "" });
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <label style={{ marginBottom: 0 }}>Height</label>
        <UnitToggle
          options={[{ value: "ftin", label: "ft / in" }, { value: "cm", label: "cm" }]}
          value={unit}
          onChange={switchUnit}
        />
      </div>

      {unit === "ftin" ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <input
            type="number" required={required} placeholder="ft"
            value={ft} onChange={(e) => onChange({ ft: e.target.value, inch })}
          />
          <input
            type="number" required={required} placeholder="in"
            value={inch} onChange={(e) => onChange({ ft, inch: e.target.value })}
          />
        </div>
      ) : (
        <input
          type="number" required={required} placeholder="e.g. 175"
          value={cmDraft} onChange={handleCmChange}
        />
      )}
    </div>
  );
}
