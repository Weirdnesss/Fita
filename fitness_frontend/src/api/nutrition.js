import { client } from "./client";

export async function searchFoods(query, category) {
  const { data } = await client.get("/nutrition/foods/search/", {
    params: { q: query, category },
  });
  return data;
}

export async function getNutritionProfile() {
  const { data } = await client.get("/nutrition/profile/");
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

export async function deleteFoodEntry(id) {
  await client.delete(`/nutrition/entries/${id}/`);
}
