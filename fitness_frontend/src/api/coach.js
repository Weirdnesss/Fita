import { client } from "./client";

export async function listChats() {
  const { data } = await client.get("/coach/chats/");
  return data;
}

export async function createChat() {
  const { data } = await client.post("/coach/chats/", {});
  return data;
}

export async function getChat(id) {
  const { data } = await client.get(`/coach/chats/${id}/`);
  return data;
}

export async function deleteChat(id) {
  await client.delete(`/coach/chats/${id}/`);
}

export async function sendMessage(chatId, content) {
  const { data } = await client.post(`/coach/chats/${chatId}/messages/`, { content });
  return data;
}
