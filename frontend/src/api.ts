import axios from "axios";
import type { Product, ProductList, ProductPayload } from "./types";

const http = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

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
