export const PASSWORD_RESET_PENDING_KEY = "vat-ai-password-reset-pending";

export interface PendingPasswordReset {
  email: string;
  requestId: string;
  expiresAt: number;
  resendAt: number;
}

// Only pending request metadata is retained; never codes, passwords or reset tokens.
export function readPendingPasswordReset(raw: string | null, now: number): PendingPasswordReset | null {
  try {
    const value = JSON.parse(raw ?? "null");
    if (!value || typeof value.email !== "string" || !value.email.includes("@") ||
        typeof value.requestId !== "string" || !/^[0-9a-f-]{36}$/i.test(value.requestId) ||
        !Number.isFinite(value.expiresAt) || value.expiresAt <= now ||
        !Number.isFinite(value.resendAt)) return null;
    return { email: value.email, requestId: value.requestId, expiresAt: value.expiresAt, resendAt: value.resendAt };
  } catch { return null; }
}
