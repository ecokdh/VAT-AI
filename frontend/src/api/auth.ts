import { apiClient } from "./client";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  created_at: string;
  business: BusinessProfile | null;
}

export interface BusinessProfile {
  id: string;
  user_id: string;
  business_number: string;
  business_name: string | null;
  business_status: string | null;
  business_status_code: string | null;
  tax_type: string | null;
  tax_type_code: string | null;
  end_date: string | null;
  verification_status: string;
  verified_at: string | null;
  created_at: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  business_name: string;
  business_number: string;
}

export interface AuthResponse {
  access_token: string;
  user: AuthUser;
}

export function login(email: string, password: string) {
  return apiClient.post<AuthResponse>("/auth/login", { email, password }).then((res) => res.data);
}

export function register(data: RegisterRequest) {
  return apiClient.post<AuthResponse>("/auth/register", data).then((res) => res.data);
}

export function getMe() {
  return apiClient.get<AuthUser>("/auth/me").then((res) => res.data);
}
