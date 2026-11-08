import UnitToggle from "./UnitToggle";
import { useThemePreference } from "../theme";

export default function ThemeToggle() {
  const [theme, setTheme] = useThemePreference();
  return (
    <UnitToggle
      options={[
        { value: "light", label: "Light" },
        { value: "dark", label: "Dark" },
        { value: "system", label: "System" },
      ]}
      value={theme}
      onChange={setTheme}
    />
  );
}