import { client } from "./client";

export async function listResources({ category, q } = {}) {
  const params = {};
  if (category) params.category = category;
  if (q) params.q = q;
  const { data } = await client.get("/resources/", { params });
  return data;
}