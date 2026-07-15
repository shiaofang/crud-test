export interface Product {
  id: number;
  name: string;
  description: string | null;
  price: number;
  stock: number;
  created_at: string;
  updated_at: string;
}

export interface ProductPayload {
  name: string;
  description: string | null;
  price: number;
  stock: number;
}

export interface ProductList {
  total: number;
  items: Product[];
}

export interface User {
  id: number;
  username: string;
  email: string | null;
  created_at: string;
}

export interface RegisterPayload {
  username: string;
  password: string;
  email?: string | null;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  /** 助手思考 / 工具调用过程，不回传给模型 */
  steps?: string[];
}

export interface ChatRequest {
  message: string;
  history?: ChatMessage[];
}
