import { useState } from "react";
import { kgToLbs, lbsToKg } from "../lib/profile";
import UnitToggle from "./UnitToggle";

// Backend only ever stores/accepts kg (current_weight_kg, goal_weight_kg,
// WeightLog.weight_kg -- see accounts/models.py). lbs is a frontend-only
// convenience: convert to kg on every change, same pattern as HeightField.
export default function WeightField({
  label = "Weight",
  kg,
  onChange,
  required = false,
  placeholder,
  autoFocus = false,
  defaultUnit = "kg",
  allowToggle = true,
}) {
  const [unit, setUnit] = useState(defaultUnit);
  const [lbsDraft, setLbsDraft] = useState(() => (kg ? String(kgToLbs(Number(kg))) : ""));

  function switchUnit(next) {
    if (next === unit) return;
    if (next === "lbs") {
      setLbsDraft(kg ? String(kgToLbs(Number(kg))) : "");
    }
    setUnit(next);
  }

  function handleLbsChange(e) {
    const raw = e.target.value;
    setLbsDraft(raw);
    const lbs = Number(raw);
    onChange(raw !== "" && !Number.isNaN(lbs) && lbs > 0 ? String(lbsToKg(lbs)) : "");
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <label style={{ marginBottom: 0 }}>{label}</label>
        {allowToggle ? (
          <UnitToggle
            options={[{ value: "kg", label: "kg" }, { value: "lbs", label: "lbs" }]}
            value={unit}
            onChange={switchUnit}
          />
        ) : (
          <span style={{ fontSize: 11, color: "var(--text-faint)" }}>{unit}</span>
        )}
      </div>

      {unit === "kg" ? (
        <input
          type="number" step="0.1" required={required} placeholder={placeholder} autoFocus={autoFocus}
          value={kg} onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          type="number" step="0.1" required={required} placeholder={placeholder} autoFocus={autoFocus}
          value={lbsDraft} onChange={handleLbsChange}
        />
      )}
    </div>
  );
}
