import { client } from "./client";

const KG_PER_LB = 0.45359237;

export function kgToLb(kg) {
  return Math.round((kg / KG_PER_LB) * 100) / 100;
}

export function lbToKg(lb) {
  return Math.round(lb * KG_PER_LB * 100) / 100;
}

export async function searchExercises(query) {
  const { data } = await client.get("/workouts/exercises/search/", { params: { q: query } });
  return data.results;
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