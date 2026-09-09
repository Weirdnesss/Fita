import { client, getTokens, setTokens, clearTokens } from "./client";

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

export async function logout() {
  // Blacklist the refresh token server-side so it can't be reused (e.g.
  // if it leaked) even though it's still within its 7-day lifetime.
  // Best-effort: still clear local tokens even if this call fails (e.g.
  // offline, token already expired) so the user is logged out either way.
  const tokens = getTokens();
  try {
    if (tokens?.refresh) {
      await client.post("/accounts/logout/", { refresh: tokens.refresh });
    }
  } catch {
    // ignored -- see comment above
  } finally {
    clearTokens();
  }
}

export async function getMe() {
  const { data } = await client.get("/accounts/me/");
  return data;
}

export async function updateProfile(fields) {
  const { data } = await client.patch("/accounts/profile/", fields);
  return data;
}

// logged_at is optional (YYYY-MM-DD) -- defaults to today on the
// backend. Logging again for a date that already has an entry
// updates it in place rather than creating a duplicate.
export async function logWeight({ weightKg, loggedAt }) {
  const body = { weight_kg: weightKg };
  if (loggedAt) body.logged_at = loggedAt;
  const { data } = await client.post("/accounts/weight-logs/", body);
  return data;
}

export async function listWeightLogs() {
  const { data } = await client.get("/accounts/weight-logs/");
  return data;
}

export async function deleteWeightLog(id) {
  await client.delete(`/accounts/weight-logs/${id}/`);
}