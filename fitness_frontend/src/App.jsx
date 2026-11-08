import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";
import { RestTimerProvider } from "./context/RestTimerContext";
import ActiveWorkoutPill from "./components/ActiveWorkoutPill";
import RequireAuth from "./components/RequireAuth";
import AppLayout from "./components/AppLayout";
import "./lib/pwaInstall";

import Login from "./pages/auth/Login";
import Signup from "./pages/auth/Signup";
import Onboarding from "./pages/auth/Onboarding";
import ProfilePage from "./pages/ProfilePage";
import EditProfile from "./pages/EditProfile";

import WorkoutsDashboard from "./pages/workouts/WorkoutsDashboard";
import TemplateEditor from "./pages/workouts/TemplateEditor";
import ActiveWorkout from "./pages/workouts/ActiveWorkout";
import WorkoutComplete from "./pages/workouts/WorkoutComplete";
import HistoryDetail from "./pages/workouts/HistoryDetail";

import NutritionDashboard from "./pages/nutrition/NutritionDashboard";
import FoodSearch from "./pages/nutrition/FoodSearch";
import FoodSuggestions from "./pages/nutrition/FoodSuggestions";
import CustomFoodForm from "./pages/nutrition/CustomFoodForm";
import NutritionSettings from "./pages/nutrition/NutritionSettings";

import ChatList from "./pages/coach/ChatList";
import ChatDetail from "./pages/coach/ChatDetail";

import ReportsList from "./pages/progress/ReportsList";
import ReportDetail from "./pages/progress/ReportDetail";
import ReportSettings from "./pages/progress/ReportSettings";

import ResourcesList from "./pages/resources/ResourcesList";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <RestTimerProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route
              path="/onboarding"
              element={
                <RequireAuth>
                  <Onboarding />
                </RequireAuth>
              }
            />
            <Route
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/profile/edit" element={<EditProfile />} />

              <Route path="/workouts" element={<WorkoutsDashboard />} />
              <Route path="/workouts/new" element={<TemplateEditor />} />
              <Route path="/workouts/templates/:id" element={<TemplateEditor />} />
              <Route path="/workouts/templates/:id/start" element={<ActiveWorkout />} />
              <Route path="/workouts/complete" element={<WorkoutComplete />} />
              <Route path="/workouts/history/:id" element={<HistoryDetail />} />
              <Route path="/nutrition" element={<NutritionDashboard />} />
              <Route path="/nutrition/search" element={<FoodSearch />} />
              <Route path="/nutrition/suggestions" element={<FoodSuggestions />} />
              <Route path="/nutrition/foods/custom" element={<CustomFoodForm />} />
              <Route path="/nutrition/settings" element={<NutritionSettings />} />

              <Route path="/coach" element={<ChatList />} />
              <Route path="/coach/:id" element={<ChatDetail />} />

              <Route path="/progress" element={<ReportsList />} />
              <Route path="/progress/settings" element={<ReportSettings />} />
              <Route path="/progress/:id" element={<ReportDetail />} />

              <Route path="/resources" element={<ResourcesList />} />
            </Route>

            <Route path="/" element={<Navigate to="/profile" replace />} />
            <Route path="*" element={<Navigate to="/profile" replace />} />
          </Routes>
          <ActiveWorkoutPill />
          </RestTimerProvider>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}