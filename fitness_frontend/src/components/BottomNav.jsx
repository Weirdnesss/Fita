import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/profile", label: "Profile", icon: ProfileIcon },
  { to: "/workouts", label: "Workouts", icon: WorkoutIcon },
  { to: "/coach", label: "Assistant", icon: AssistantIcon },
  { to: "/nutrition", label: "Nutrition", icon: NutritionIcon },
  { to: "/progress", label: "Progress", icon: ProgressIcon },
];

export default function BottomNav() {
  return (
    <nav style={styles.nav}>
      {TABS.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          style={({ isActive }) => ({
            ...styles.tab,
            color: isActive ? "var(--chili)" : "var(--text-faint)",
          })}
        >
          <Icon />
          <span style={styles.label}>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

const styles = {
  nav: {
    position: "fixed",
    bottom: 0,
    left: "50%",
    transform: "translateX(-50%)",
    width: "100%",
    maxWidth: "var(--max-width)",
    height: "var(--nav-height)",
    background: "var(--bg-raised)",
    borderTop: "1px solid var(--border)",
    display: "flex",
    zIndex: 10,
  },
  tab: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
  },
  label: {
    fontSize: 10,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.03em",
  },
};

function iconProps() {
  return { width: 22, height: 22, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
}

function ProfileIcon() {
  return (
    <svg {...iconProps()}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-4 4-6 8-6s8 2 8 6" />
    </svg>
  );
}
function WorkoutIcon() {
  return (
    <svg {...iconProps()}>
      <path d="M6.5 6.5l11 11M4 9l3-3 2 2-3 3-2-2zm9 9l3-3 2 2-3 3-2-2zM2 20l3-3M18.5 5.5L21 3" />
    </svg>
  );
}
function AssistantIcon() {
  return (
    <svg {...iconProps()}>
      <path d="M21 11.5a8.5 8.5 0 01-8.5 8.5H4l1.8-3.6A8.5 8.5 0 1121 11.5z" />
    </svg>
  );
}
function NutritionIcon() {
  return (
    <svg {...iconProps()}>
      <path d="M18 8c0 4-2.7 8-6 8s-6-4-6-8a6 6 0 0112 0z" />
      <path d="M12 2c1 1.5 1 3 0 4" />
    </svg>
  );
}
function ProgressIcon() {
  return (
    <svg {...iconProps()}>
      <path d="M4 20V10M12 20V4M20 20v-6" />
    </svg>
  );
}
