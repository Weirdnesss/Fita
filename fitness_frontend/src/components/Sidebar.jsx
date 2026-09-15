import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/profile", label: "Profile", icon: ProfileIcon },
  { to: "/workouts", label: "Workouts", icon: WorkoutIcon },
  { to: "/coach", label: "Assistant", icon: AssistantIcon },
  { to: "/nutrition", label: "Nutrition", icon: NutritionIcon },
  { to: "/progress", label: "Progress", icon: ProgressIcon },
  { to: "/resources", label: "Resources", icon: ResourcesIcon },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        FITA
      </div>

      <nav className="sidebar-nav" aria-label="Main navigation">
        {TABS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `sidebar-link${isActive ? " active" : ""}`
            }
          >
            <Icon />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

function iconProps() {
  return {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };
}

function ProfileIcon() {
  return (
    <svg {...iconProps()}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 3-7 8-7s8 3 8 7" />
    </svg>
  );
}

function WorkoutIcon() {
  return (
    <svg {...iconProps()}>
      <path d="M6 8v8" />
      <path d="M18 8v8" />
      <path d="M3 10v4" />
      <path d="M21 10v4" />
      <path d="M6 12h12" />
    </svg>
  );
}

function AssistantIcon() {
  return (
    <svg {...iconProps()}>
      <path d="M12 3a7 7 0 0 0-7 7v4a3 3 0 0 0 3 3h1v-6H6" />
      <path d="M12 3a7 7 0 0 1 7 7v4a3 3 0 0 1-3 3h-1v-6h3" />
      <path d="M9 21h6" />
    </svg>
  );
}

function NutritionIcon() {
  return (
    <svg {...iconProps()}>
      <path d="M7 3v8" />
      <path d="M4 3v5a3 3 0 0 0 6 0V3" />
      <path d="M7 11v10" />
      <path d="M17 3v18" />
      <path d="M17 3c3 2 3 6 0 8" />
    </svg>
  );
}

function ProgressIcon() {
  return (
    <svg {...iconProps()}>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="m7 15 4-4 3 2 5-6" />
    </svg>
  );
}

function ResourcesIcon() {
  return (
    <svg {...iconProps()}>
      <path d="M4 5a2 2 0 0 1 2-2h13v17H6a2 2 0 0 0-2 2z" />
      <path d="M4 5v15" />
      <path d="M8 7h7" />
      <path d="M8 11h7" />
    </svg>
  );
}