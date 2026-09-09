import axios from "axios";

// Point this at your Django backend. Override with a .env file:
// VITE_API_BASE_URL=http://127.0.0.1:8000
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const client = axios.create({ baseURL: BASE_URL });

function getTokens() {
  const raw = localStorage.getItem("fitness_assistant_tokens");
  return raw ? JSON.parse(raw) : null;
}

function setTokens(tokens) {
  localStorage.setItem("fitness_assistant_tokens", JSON.stringify(tokens));
}

function clearTokens() {
  localStorage.removeItem("fitness_assistant_tokens");
}

client.interceptors.request.use((config) => {
  const tokens = getTokens();
  if (tokens?.access) {
    config.headers.Authorization = `Bearer ${tokens.access}`;
  }
  return config;
});

// On a 401, try refreshing the access token once, then retry the
// original request. If refresh also fails, clear tokens and let the
// caller's normal error handling redirect to login.
let refreshPromise = null;

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status !== 401 || original._retried) {
      return Promise.reject(error);
    }
    const tokens = getTokens();
    if (!tokens?.refresh) {
      clearTokens();
      return Promise.reject(error);
    }
    original._retried = true;

    try {
      if (!refreshPromise) {
        refreshPromise = axios
          .post(`${BASE_URL}/accounts/login/refresh/`, { refresh: tokens.refresh })
          .then((res) => {
            // The backend rotates refresh tokens on every use and
            // blacklists the old one (see accounts SIMPLE_JWT settings),
            // so the response's `refresh` field -- not the one we sent --
            // is the only one still valid. Keeping the stale `tokens.refresh`
            // here would make the NEXT refresh attempt fail with
            // "Token is blacklisted" and force-log the user out.
            setTokens({ access: res.data.access, refresh: res.data.refresh ?? tokens.refresh });
            return res.data.access;
          })
          .finally(() => {
            refreshPromise = null;
          });
      }
      const newAccess = await refreshPromise;
      original.headers.Authorization = `Bearer ${newAccess}`;
      return client(original);
    } catch (refreshError) {
      clearTokens();
      return Promise.reject(error);
    }
  }
);

export { client, getTokens, setTokens, clearTokens };