import { apiClient } from "./client";
import type { TaxProfileInput } from "./transactions";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  created_at: string;
  ocr_guide_seen: boolean;
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
  terms_accepted: boolean;
  privacy_accepted: boolean;
  marketing_accepted: boolean;
  tax_profile?: TaxProfileInput;
}

export interface EmailAvailabilityResponse {
  available: boolean;
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

export function checkEmailAvailability(email: string) {
  return apiClient
    .post<EmailAvailabilityResponse>("/auth/email-availability", { email })
    .then((res) => res.data);
}

export function getMe() {
  return apiClient.get<AuthUser>("/auth/me").then((res) => res.data);
}

export const requestPasswordReset = (email: string) => apiClient.post<{message: string}>("/auth/forgot-password", {email}).then(r => r.data);
export const resetPassword = (token: string, password: string) => apiClient.post<{message: string}>("/auth/reset-password", {token, password}).then(r => r.data);
export const markOcrGuideSeen = () => apiClient.post<AuthUser>("/auth/ocr-guide-seen").then(r => r.data);
