import { apiClient } from "./client";

export interface BusinessVerificationResponse {
  business_number: string;
  business_status: string;
  business_status_code: string;
  tax_type: string;
  tax_type_code: string;
  end_date: string | null;
  verified: boolean;
}

export function verifyBusiness(businessNumber: string) {
  return apiClient
    .post<BusinessVerificationResponse>("/business/verify", { business_number: businessNumber })
    .then((res) => res.data);
}

export const verifyBusinessIdentity = (business_number: string, representative_name: string, business_start_date: string) =>
  apiClient.post<{verified: boolean}>("/business/verify-identity", {business_number, representative_name, business_start_date}).then(r => r.data);
