import { useState } from "react";
import { cmToFtIn, ftInToCm } from "../lib/profile";
import UnitToggle from "./UnitToggle";

// Backend stores a single height_cm field (see accounts/models.py) --
// metric-native, same pattern as WeightField's kg. ft/in mode is a
// frontend-only convenience: converted to cm on every keystroke, same
// as WeightField converts lbs to kg.
export default function HeightField({ cm, onChange, required = false, defaultUnit = "ftin", allowToggle = true }) {
  const [unit, setUnit] = useState(defaultUnit);
  const [ftDraft, setFtDraft] = useState(() => (cm ? cmToFtIn(Number(cm)).ft : ""));
  const [inDraft, setInDraft] = useState(() => (cm ? cmToFtIn(Number(cm)).inch : ""));

  function switchUnit(next) {
    if (next === unit) return;
    if (next === "ftin" && cm) {
      const { ft, inch } = cmToFtIn(Number(cm));
      setFtDraft(ft);
      setInDraft(inch);
    }
    setUnit(next);
  }

  function handleFtInChange(newFt, newIn) {
    setFtDraft(newFt);
    setInDraft(newIn);
    if (newFt !== "" || newIn !== "") {
      onChange(ftInToCm(newFt, newIn));
    } else {
      onChange("");
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <label style={{ marginBottom: 0 }}>Height</label>
        {allowToggle ? (
          <UnitToggle
            options={[{ value: "cm", label: "cm" }, { value: "ftin", label: "ft / in" }]}
            value={unit}
            onChange={switchUnit}
          />
        ) : (
          <span style={{ fontSize: 11, color: "var(--text-faint)" }}>{unit === "ftin" ? "ft / in" : "cm"}</span>
        )}
      </div>

      {unit === "ftin" ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <input
            type="number" required={required} placeholder="ft"
            value={ftDraft} onChange={(e) => handleFtInChange(e.target.value, inDraft)}
          />
          <input
            type="number" required={required} placeholder="in"
            value={inDraft} onChange={(e) => handleFtInChange(ftDraft, e.target.value)}
          />
        </div>
      ) : (
        <input
          type="number" required={required} placeholder="e.g. 175"
          value={cm} onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}
