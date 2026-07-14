import axios from "axios";
import type {
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
