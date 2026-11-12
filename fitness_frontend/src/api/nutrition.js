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

// Dates in a month ("2026-11") that have at least one logged food.
export async function getLoggedDates(month) {
  const { data } = await client.get("/nutrition/daily/dates/", { params: { month } });
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

export async function getFoodSuggestions({ mealType, date, limit = 4, exclude = [], explain = true } = {}) {
  // Rule-picked foods that fit what's left of the day's goals; the LLM only
  // re-ranks/explains them. Each item: { food, servings, amount_label,
  // calories, protein_g, carbs_g, fat_g, reason, reason_source }.
  // `exclude` = food ids already shown, for "show different ideas".
  const { data } = await client.get("/nutrition/suggestions/", {
    params: {
      meal_type: mealType,
      date,
      limit,
      explain,
      exclude: exclude.length ? exclude.join(",") : undefined,
    },
  });
  return data; // { meal_type, date, remaining, suggestions, message? }
}

// A user's own foods (private to them) -- for anything missing from the database.
export async function createCustomFood(fields) {
  const { data } = await client.post("/nutrition/foods/custom/", fields);
  return data; // same shape as a search result
}

export async function updateCustomFood(id, fields) {
  const { data } = await client.patch(`/nutrition/foods/custom/${id}/`, fields);
  return data;
}

export async function deleteCustomFood(id) {
  // 409 if the food has already been logged (the backend protects history).
  await client.delete(`/nutrition/foods/custom/${id}/`);
}

export async function getMealSuggestions({ mealType, date, limit = 3, exclude = [], explain = true } = {}) {
  // Whole-plate ideas (a protein + a carb + a veg or fruit), portioned to fit
  // what's left today. Each meal: { items: [{ food, role, servings,
  // amount_label, calories, protein_g, carbs_g, fat_g }], totals, reason,
  // reason_source }. `exclude` = food ids already shown (skipped as the main item).
  const { data } = await client.get("/nutrition/suggestions/meals/", {
    params: {
      meal_type: mealType,
      date,
      limit,
      explain,
      exclude: exclude.length ? exclude.join(",") : undefined,
    },
  });
  return data; // { meal_type, date, remaining, meals, message? }
}

export async function logFoodsBulk({ mealType, date, items }) {
  // Logs several foods to one meal at once, all-or-nothing ("Add all" on a plate).
  // items: [{ foodItemId, servings }]
  const { data } = await client.post("/nutrition/entries/bulk/", {
    meal_type: mealType,
    date,
    items: items.map((i) => ({ food_item: i.foodItemId, servings: i.servings })),
  });
  return data; // the created entries
}
