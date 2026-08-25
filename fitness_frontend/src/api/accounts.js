import { client, setTokens, clearTokens } from "./client";

export async function register({ email, firstName, lastName, password, confirmPassword }) {
  const { data } = await client.post("/accounts/register/", {
    email,
    first_name: firstName,
    last_name: lastName,
    password,
    confirm_password: confirmPassword,
  });
  return data;
}

export async function login({ email, password }) {
  const { data } = await client.post("/accounts/login/", { email, password });
  setTokens(data);
  return data;
}

export function logout() {
  clearTokens();
}

export async function getMe() {
  const { data } = await client.get("/accounts/me/");
  return data;
}

export async function updateProfile(fields) {
  const { data } = await client.patch("/accounts/profile/", fields);
  return data;
}
