import test from "node:test";
import assert from "node:assert/strict";
import { readPendingPasswordReset } from "../src/hooks/passwordResetState.ts";

const pending = { email: "owner@example.com", requestId: "11111111-1111-4111-8111-111111111111", expiresAt: 600000, resendAt: 60000 };
test("메일 확인 후 새로고침해도 유효한 인증 코드 입력 단계를 복원한다", () => {
  assert.deepEqual(readPendingPasswordReset(JSON.stringify(pending), 1000), pending);
});
test("만료되거나 손상된 요청은 복원하지 않는다", () => {
  for (const raw of [null, "{", "null", JSON.stringify({ ...pending, expiresAt: 1000 }), JSON.stringify({ ...pending, requestId: "invalid" })]) {
    assert.equal(readPendingPasswordReset(raw, 1000), null);
  }
});
test("인증 코드·비밀번호·재설정 토큰은 복원 대상에 포함하지 않는다", () => {
  assert.deepEqual(readPendingPasswordReset(JSON.stringify({ ...pending, code: "123456", password: "unused", token: "unused" }), 1000), pending);
});
