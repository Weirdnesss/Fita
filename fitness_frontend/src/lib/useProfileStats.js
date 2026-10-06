import { useEffect, useState } from "react";
import { getDailyEntry, getNutritionProfile, getNutritionTrends } from "../api/nutrition";
import { getWorkoutTrends } from "../api/workouts";
import { listReports, getReportSettings } from "../api/progress";

function todayStr() {
  return new Date().toLocaleDateString("en-CA"); // local YYYY-MM-DD
}

const EMPTY = {
  workoutsThisWeek: 0,
  workoutStreak: 0,
  streak: 0, // nutrition logging streak
  caloriesToday: 0,
  calorieTarget: 0,
};

export function useProfileStats() {
  const [stats, setStats] = useState(EMPTY);
  const [latestReport, setLatestReport] = useState(null);
  const [reportSettings, setReportSettings] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [daily, goals, nutTrends, wkTrends, reports, rSettings] = await Promise.allSettled([
        getDailyEntry(todayStr()),
        getNutritionProfile(),
        getNutritionTrends("week"),
        getWorkoutTrends("week"),
        listReports(),
        getReportSettings(),
      ]);
      if (cancelled) return;

      const next = { ...EMPTY };
      if (daily.status === "fulfilled") next.caloriesToday = Math.round(daily.value.total_calories || 0);
      if (goals.status === "fulfilled") next.calorieTarget = goals.value.daily_calories_goal || 0;
      if (nutTrends.status === "fulfilled") next.streak = nutTrends.value.current_streak || 0;
      if (wkTrends.status === "fulfilled") {
        next.workoutsThisWeek = wkTrends.value.total_workouts || 0;
        next.workoutStreak = wkTrends.value.current_streak || 0;
      }
      if (reports.status === "fulfilled") {
        const list = Array.isArray(reports.value) ? reports.value : reports.value.results || [];
        // same rule as the Reports page: newest *successful* report
        setLatestReport(list.find((r) => r.status === "generated") || null);
      }
      if (rSettings.status === "fulfilled") setReportSettings(rSettings.value);

      setStats(next);
      setStatsLoading(false);
    }

    load();
    return () => { cancelled = true; };
  }, []);

  return { stats, latestReport, reportSettings, statsLoading };
}