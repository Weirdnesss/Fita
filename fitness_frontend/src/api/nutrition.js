import { client } from "./client";

export async function searchFoods(query, category, offset = 0) {
  const { data } = await client.get("/nutrition/foods/search/", {
    params: { q: query, category, offset },
  });
  return data; // { count, results, next_offset }
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

export async function updateFoodEntry(id, { mealType, servings, foodItemId, date } = {}) {
  const payload = {};
  if (mealType !== undefined) payload.meal_type = mealType;
  if (servings !== undefined) payload.servings = servings;
  if (foodItemId !== undefined) payload.food_item = foodItemId;
  if (date !== undefined) payload.date = date;
  const { data } = await client.patch(`/nutrition/entries/${id}/`, payload);
  return data;
}

export async function deleteFoodEntry(id) {
  await client.delete(`/nutrition/entries/${id}/`);
}

export async function getNutritionTrends(period = "week") {
  const { data } = await client.get("/nutrition/trends/", { params: { period } });
  return data; // { period, days, days_logged, averages, current_streak }
}
