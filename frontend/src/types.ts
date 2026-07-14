export interface Product {
  id: number;
  name: string;
  description: string | null;
  price: number;
  stock: number;
  clickCount: number;
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
