import axios from "axios";
import type {
  ChatRequest,
  LoginPayload,
  Product,
  ProductList,
  ProductPayload,
  RegisterPayload,
  Token,
  User,
} from "./types";

const http = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

export function setAuthToken(token: string | null) {
  if (token) {
    http.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete http.defaults.headers.common.Authorization;
  }
}

const savedToken = localStorage.getItem("access_token");
if (savedToken) {
  setAuthToken(savedToken);
}

export const authApi = {
  register(data: RegisterPayload) {
    return http.post<User>("/auth/register", data).then((r) => r.data);
  },
  login(data: LoginPayload) {
    return http.post<Token>("/auth/login", data).then((r) => r.data);
  },
  me() {
    return http.get<User>("/auth/me").then((r) => r.data);
  },
};

export const productApi = {
  list(params: { page: number; page_size: number; keyword?: string }) {
    return http.get<ProductList>("/products", { params }).then((r) => r.data);
  },
  create(data: ProductPayload) {
    return http.post<Product>("/products", data).then((r) => r.data);
  },
  update(id: number, data: ProductPayload) {
    return http.put<Product>(`/products/${id}`, data).then((r) => r.data);
  },
  remove(id: number) {
    return http.delete(`/products/${id}`).then((r) => r.data);
  },
};

export const hotProductApi = {
  list(params?: { keyword?: string }) {
    return http.get<ProductList>("/hot-products", { params }).then((r) => r.data);
  },
};

export const chatApi = {
  async stream(
    data: ChatRequest,
    handlers: {
      onDelta: (delta: string) => void;
      onStatus?: (status: string) => void;
      onStatusDelta?: (delta: string) => void;
      onClearDelta?: () => void;
      onDone?: (refresh: string[]) => void;
    },
    signal?: AbortSignal,
  ) {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const token = localStorage.getItem("access_token");
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const res = await fetch("/api/chat", {
      method: "POST",
      headers,
      body: JSON.stringify(data),
      signal,
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `请求失败（${res.status}）`);
    }
    if (!res.body) {
      throw new Error("浏览器不支持流式响应");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";

      for (const chunk of chunks) {
        const line = chunk
          .split("\n")
          .map((l) => l.trim())
          .find((l) => l.startsWith("data:"));
        if (!line) continue;

        const raw = line.replace(/^data:\s*/, "");
        if (!raw || raw === "[DONE]") continue;

        let payload: {
          delta?: string;
          status?: string;
          status_delta?: string;
          clear_delta?: boolean;
          done?: boolean;
          refresh?: string[];
          error?: string;
        };
        try {
          payload = JSON.parse(raw);
        } catch {
          continue;
        }

        if (payload.error) {
          throw new Error(payload.error);
        }
        if (payload.clear_delta) {
          handlers.onClearDelta?.();
        }
        if (payload.status !== undefined) {
          handlers.onStatus?.(payload.status);
        }
        if (payload.status_delta) {
          handlers.onStatusDelta?.(payload.status_delta);
        }
        if (payload.delta) {
          handlers.onDelta(payload.delta);
        }
        if (payload.done) {
          handlers.onDone?.(payload.refresh ?? []);
        }
      }
    }
  },
};
