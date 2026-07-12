import { computed, ref } from "vue";
import { authApi, setAuthToken } from "../api";
import type { User } from "../types";

const TOKEN_KEY = "access_token";

const token = ref<string | null>(localStorage.getItem(TOKEN_KEY));
const user = ref<User | null>(null);
const initialized = ref(false);

export function useAuth() {
  const isLoggedIn = computed(() => !!token.value && !!user.value);

  async function init() {
    if (initialized.value) return;
    if (token.value) {
      setAuthToken(token.value);
      try {
        user.value = await authApi.me();
      } catch {
        logout();
      }
    }
    initialized.value = true;
  }

  async function login(username: string, password: string) {
    const res = await authApi.login({ username, password });
    token.value = res.access_token;
    localStorage.setItem(TOKEN_KEY, res.access_token);
    setAuthToken(res.access_token);
    user.value = await authApi.me();
  }

  async function register(username: string, password: string, email?: string) {
    await authApi.register({ username, password, email: email || null });
    await login(username, password);
  }

  function logout() {
    token.value = null;
    user.value = null;
    localStorage.removeItem(TOKEN_KEY);
    setAuthToken(null);
  }

  return {
    token,
    user,
    initialized,
    isLoggedIn,
    init,
    login,
    register,
    logout,
  };
}
