import { apiClient } from "./client";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  user: AuthUser;
}

export function login(email: string, password: string) {
  return apiClient.post<AuthResponse>("/auth/login", { email, password }).then((res) => res.data);
}

export function register(email: string, password: string, name: string) {
  return apiClient.post<AuthResponse>("/auth/register", { email, password, name }).then((res) => res.data);
}

export function getMe() {
  return apiClient.get<AuthUser>("/auth/me").then((res) => res.data);
}
