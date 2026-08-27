import { client } from "./client";

export async function searchFoods(query, category) {
  const { data } = await client.get("/nutrition/foods/search/", {
    params: { q: query, category },
  });
  return data; // { count, results }
}

export async function getNutritionProfile() {
  const { data } = await client.get("/nutrition/profile/");
  return data;
}

export async function getSuggestedGoals() {
  // Throws with err.response.status === 422 and err.response.data.missing_fields
  // if the accounts Profile doesn't have weight/height/age/gender yet.
  const { data } = await client.get("/nutrition/goals/suggested/");
  return data;
}

export async function updateNutritionProfile(fields) {
  const { data } = await client.patch("/nutrition/profile/", fields);
  return data;
}

export async function getDailyEntry(date) {
  const { data } = await client.get("/nutrition/daily/", { params: date ? { date } : {} });
  return data;
}

export async function logFood({ foodItemId, mealType, servings, date }) {
  const { data } = await client.post("/nutrition/entries/", {
    food_item: foodItemId,
    meal_type: mealType,
    servings,
    date,
  });
  return data;
}

export async function updateFoodEntry(id, { mealType, servings }) {
  const payload = {};
  if (mealType !== undefined) payload.meal_type = mealType;
  if (servings !== undefined) payload.servings = servings;
  const { data } = await client.patch(`/nutrition/entries/${id}/`, payload);
  return data;
}

export async function deleteFoodEntry(id) {
  await client.delete(`/nutrition/entries/${id}/`);
}
