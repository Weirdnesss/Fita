import { useState } from "react";

const STORAGE_KEY = "fita_theme";
const THEME_COLORS = { dark: "#15171b", light: "#f3f1ec" };

// "dark" | "light" | "system". Defaults to dark so existing users and
// testers see no change until they pick something else.
export function getThemePreference() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "system" ? v : "dark";
  } catch {
    return "dark";
  }
}

function systemTheme() {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function applyTheme(pref) {
  const resolved = pref === "system" ? systemTheme() : pref;
  document.documentElement.setAttribute("data-theme", resolved);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", THEME_COLORS[resolved]);
}

// Call once at startup (main.jsx). Also follows the OS setting live
// while the preference is "system".
export function initTheme() {
  applyTheme(getThemePreference());
  const mq = window.matchMedia?.("(prefers-color-scheme: light)");
  mq?.addEventListener?.("change", () => {
    if (getThemePreference() === "system") applyTheme("system");
  });
}

export function setThemePreference(pref) {
  try {
    localStorage.setItem(STORAGE_KEY, pref);
  } catch {
    /* storage unavailable -- the choice just won't persist */
  }
  applyTheme(pref);
}

export function useThemePreference() {
  const [pref, setPref] = useState(getThemePreference);
  function update(next) {
    setPref(next);
    setThemePreference(next);
  }
  return [pref, update];
}