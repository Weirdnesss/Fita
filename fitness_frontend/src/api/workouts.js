import { client } from "./client";

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

export async function listHistory() {
  const { data } = await client.get("/workouts/history/");
  return data;
}

export async function finishWorkout({ templateTitle, startedAt, exercises }) {
  const { data } = await client.post("/workouts/history/", {
    template_title: templateTitle,
    started_at: startedAt,
    exercises,
  });
  return data;
}
