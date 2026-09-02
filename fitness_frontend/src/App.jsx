import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";
import RequireAuth from "./components/RequireAuth";
import AppLayout from "./components/AppLayout";

import Login from "./pages/auth/Login";
import Signup from "./pages/auth/Signup";
import ProfilePage from "./pages/ProfilePage";

import WorkoutsDashboard from "./pages/workouts/WorkoutsDashboard";
import TemplateEditor from "./pages/workouts/TemplateEditor";
import ActiveWorkout from "./pages/workouts/ActiveWorkout";
import HistoryDetail from "./pages/workouts/HistoryDetail";

import NutritionDashboard from "./pages/nutrition/NutritionDashboard";
import FoodSearch from "./pages/nutrition/FoodSearch";
import NutritionSettings from "./pages/nutrition/NutritionSettings";

import ChatList from "./pages/coach/ChatList";
import ChatDetail from "./pages/coach/ChatDetail";

import ReportsList from "./pages/progress/ReportsList";
import ReportDetail from "./pages/progress/ReportDetail";
import ReportSettings from "./pages/progress/ReportSettings";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />

            <Route
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              <Route path="/profile" element={<ProfilePage />} />

              <Route path="/workouts" element={<WorkoutsDashboard />} />
              <Route path="/workouts/new" element={<TemplateEditor />} />
              <Route path="/workouts/templates/:id" element={<TemplateEditor />} />
              <Route path="/workouts/templates/:id/start" element={<ActiveWorkout />} />
              <Route path="/workouts/history/:id" element={<HistoryDetail />} />

              <Route path="/nutrition" element={<NutritionDashboard />} />
              <Route path="/nutrition/search" element={<FoodSearch />} />
              <Route path="/nutrition/settings" element={<NutritionSettings />} />

              <Route path="/coach" element={<ChatList />} />
              <Route path="/coach/:id" element={<ChatDetail />} />

              <Route path="/progress" element={<ReportsList />} />
              <Route path="/progress/settings" element={<ReportSettings />} />
              <Route path="/progress/:id" element={<ReportDetail />} />
            </Route>

            <Route path="/" element={<Navigate to="/profile" replace />} />
            <Route path="*" element={<Navigate to="/profile" replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
