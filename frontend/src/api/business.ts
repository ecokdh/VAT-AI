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
