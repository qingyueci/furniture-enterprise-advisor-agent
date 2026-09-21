import http, { type ApiSuccess } from './http'

export type ProductType = 'INTERNAL' | 'COMPETITOR'
export type PriceType = 'GUIDE' | 'SALES' | 'INTERNAL_QUOTE'

export interface Product {
  id: number
  product_name: string
  model: string
  category: string | null
  brand: string
  product_type: ProductType
  description: string | null
  created_at: string
  updated_at: string
}

export interface ProductListData {
  items: Product[]
  pagination: { page: number; page_size: number; total: number }
}

export interface ProductOptions { brands: string[]; categories: string[] }
export interface ProductFilters { keyword?: string; brand?: string; category?: string; product_type?: ProductType; include_deleted?: boolean; page?: number; page_size?: number }
export interface ProductInput { product_name: string; model: string; category?: string | null; brand: string; product_type: ProductType; description?: string | null }
export interface ProductPrice { quote_spec?: string | null; pricing_unit?: string | null; included_scope?: string | null; id: number; product_id: number; price: string; currency: string; price_type: PriceType; source: string; update_time: string }
export interface ProductPricesData { product: Pick<Product, 'id' | 'product_name' | 'model'>; prices: ProductPrice[] }

export async function fetchProducts(filters: ProductFilters = {}): Promise<ProductListData> {
  const { data } = await http.get<ApiSuccess<ProductListData>>('/products', { params: filters })
  return data.data
}

export async function fetchProductOptions(): Promise<ProductOptions> {
  const { data } = await http.get<ApiSuccess<ProductOptions>>('/products/options')
  return data.data
}

export async function createProduct(payload: ProductInput): Promise<Product> {
  const { data } = await http.post<ApiSuccess<Product>>('/products', payload)
  return data.data
}

export async function updateProduct(id: number, payload: ProductInput): Promise<Product> {
  const { data } = await http.put<ApiSuccess<Product>>(`/products/${id}`, payload)
  return data.data
}

export async function deleteProduct(id: number): Promise<void> { await http.delete(`/products/${id}`) }
export async function deleteProducts(ids: number[]): Promise<void> { await http.post('/products/bulk-delete', { ids }) }
export async function restoreProduct(id: number): Promise<Product> { const { data } = await http.post<ApiSuccess<Product>>(`/products/${id}/restore`); return data.data }
export async function permanentlyDeleteProduct(id: number): Promise<void> { await http.delete(`/products/${id}/permanent`) }

export async function fetchProduct(id: number): Promise<Product> {
  const { data } = await http.get<ApiSuccess<Product>>(`/products/${id}`)
  return data.data
}

export async function fetchPrices(id: number, priceType?: PriceType): Promise<ProductPricesData> {
  const { data } = await http.get<ApiSuccess<ProductPricesData>>(`/products/${id}/price`, { params: priceType ? { price_type: priceType } : {} })
  return data.data
}
