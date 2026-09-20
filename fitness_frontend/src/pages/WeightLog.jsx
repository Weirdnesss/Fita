import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import PageHeader from "../components/PageHeader";
import { Loading } from "../components/Status";
import useWeightLogs from "../hooks/useWeightLogs";
import GoalWeightSection from "../components/weight/GoalWeightSection";
import LogWeightForm from "../components/weight/LogWeightForm";
import WeightHistoryList from "../components/weight/WeightHistoryList";
import WeightChart from "../components/weight/WeightChart";

// The detailed/archive view -- deliberately structured differently
// from the embedded components/WeightProgress.jsx summary card rather
// than just being a bigger version of it: chart and full history lead
// (this is where you come to actually look at your data), editing is
// tucked into collapsed sections below (this isn't where most visits
// are about setting things up). Built from the same shared pieces in
// components/weight/ either way, so there's one copy of the actual
// logic -- only the page-level layout differs.
export default function WeightLog() {
  const { user } = useAuth();
  const { logs, reload } = useWeightLogs();
  const [addOpen, setAddOpen] = useState(false);
  const [goalOpen, setGoalOpen] = useState(false);

  const currentGoal = user?.profile?.goal_weight_kg ?? null;
  const unitSystem = user?.profile?.unit_system || "metric";

  return (
    <div className="page page-narrow">
      <PageHeader title="Weight History" back backTo="/profile" />

      <div className="card" style={{ marginBottom: 12 }}>
        <p className="eyebrow" style={{ marginBottom: 8 }}>Trend</p>
        {logs === null && <Loading />}
        {logs !== null && logs.length < 2 && (
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>
            Log at least 2 entries to see a trend graph.
          </p>
        )}
        {logs !== null && logs.length >= 2 && (
          <WeightChart logs={logs} goalWeightKg={currentGoal} primaryGoal={user?.profile?.primary_goal} unitSystem={unitSystem} />
        )}
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <WeightHistoryList logs={logs} unitSystem={unitSystem} onDeleted={reload} heading="Full history" />
      </div>

      <CollapsibleSection title="Add entry" open={addOpen} onToggle={() => setAddOpen((o) => !o)}>
        <LogWeightForm onLogged={() => { reload(); setAddOpen(false); }} />
      </CollapsibleSection>

      <CollapsibleSection title="Edit goal weight" open={goalOpen} onToggle={() => setGoalOpen((o) => !o)}>
        <GoalWeightSection startExpanded onSaved={() => setGoalOpen(false)} />
      </CollapsibleSection>
    </div>
  );
}

function CollapsibleSection({ title, open, onToggle, children }) {
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <button
        onClick={onToggle}
        style={{ background: "none", border: "none", padding: 0, width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <h3>{title}</h3>
        <span style={{ fontSize: 12, color: "var(--text-faint)" }}>{open ? "Hide" : "Show"}</span>
      </button>
      {open && <div style={{ marginTop: 12 }}>{children}</div>}
    </div>
  );
}
