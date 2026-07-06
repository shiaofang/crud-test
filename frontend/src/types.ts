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
