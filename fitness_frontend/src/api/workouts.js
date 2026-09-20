import { client } from "./client";

const KG_PER_LB = 0.45359237;

export function kgToLb(kg) {
  return Math.round((kg / KG_PER_LB) * 100) / 100;
}

export function lbToKg(lb) {
  return Math.round(lb * KG_PER_LB * 100) / 100;
}

export async function searchExercisesPaged(query, category, offset = 0) {
  const { data } = await client.get("/workouts/exercises/search/", {
    params: { q: query, category, offset },
  });
  return data; // { count, results, next_offset, hint? }
}

export async function getExerciseCategories() {
  const { data } = await client.get("/workouts/exercises/categories/");
  return data; // ["Chest", "Legs", ...]
}

export async function listTemplates() {
  const { data } = await client.get("/workouts/templates/");
  return data;
}

export async function createTemplate({ title, kind = "main" }) {
  const { data } = await client.post("/workouts/templates/", { title, kind });
  return data;
}

export async function getTemplate(id) {
  const { data } = await client.get(`/workouts/templates/${id}/`);
  return data;
}

export async function updateTemplate(id, { title }) {
  const { data } = await client.patch(`/workouts/templates/${id}/`, { title });
  return data;
}

export async function deleteTemplate(id) {
  await client.delete(`/workouts/templates/${id}/`);
}

export async function generateWorkout() {
  const { data } = await client.post("/workouts/generate/");
  return data;
}

export async function addExerciseToTemplate(templateId, { wgerExerciseId, targetSets = 3 }) {
  const { data } = await client.post(`/workouts/templates/${templateId}/exercises/`, {
    wger_exercise_id: wgerExerciseId,
    target_sets: targetSets,
  });
  return data;
}

export async function removeExerciseFromTemplate(templateId, exerciseId) {
  const { data } = await client.delete(`/workouts/templates/${templateId}/exercises/${exerciseId}/`);
  return data;
}

export async function updateTemplateExercise(templateId, exerciseId, { targetSets, weightUnit }) {
  const body = {};
  if (targetSets !== undefined) body.target_sets = targetSets;
  if (weightUnit !== undefined) body.weight_unit = weightUnit;
  const { data } = await client.patch(`/workouts/templates/${templateId}/exercises/${exerciseId}/`, body);
  return data;
}

// reason must be one of "too_hard" | "unavailable" | "wrong" -- see
// TemplateExerciseSwapView on the backend. Unlike a full regenerate,
// this isn't limited by the weekly cooldown.
export async function swapTemplateExercise(templateId, exerciseId, reason) {
  const { data } = await client.post(
    `/workouts/templates/${templateId}/exercises/${exerciseId}/swap/`,
    { reason }
  );
  return data;
}

export async function listHistory() {
  const { data } = await client.get("/workouts/history/");
  return data;
}

export async function getHistoryDetail(id) {
  const { data } = await client.get(`/workouts/history/${id}/`);
  return data;
}

export async function finishWorkout({ templateTitle, startedAt, exercises, note }) {
  const { data } = await client.post("/workouts/history/", {
    template_title: templateTitle,
    started_at: startedAt,
    exercises,
    note: note || "",
  });
  return data;
}
export async function getWorkoutTrends(period = "week") {
  const { data } = await client.get("/workouts/trends/", { params: { period } });
  return data; // { period, days, days_logged, total_workouts, averages, current_streak }
}

export async function getExerciseFrequency() {
  const { data } = await client.get("/workouts/trends/exercises/");
  return data; // [{ name, sessions }]
}

export async function getExerciseProgression(name, period = "3months") {
  const { data } = await client.get("/workouts/trends/exercise/", { params: { name, period } });
  return data; // { exercise, period, sessions: [{ date, top_weight, top_weight_reps, total_sets }] }
}