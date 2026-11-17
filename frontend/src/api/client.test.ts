import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ApiError, apiFetch } from "./client";

const fetchMock = vi.fn<typeof fetch>();
const getToken = vi.fn(async () => "mock-token");

beforeEach(() => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  getToken.mockClear();
});

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("apiFetch calls VITE_API_BASE_URL + path with the Clerk bearer token", async () => {
  fetchMock.mockResolvedValue(jsonResponse(200, { user_id: "user_123" }));

  const body = await apiFetch<{ user_id: string }>("/api/v1/me", getToken);

  expect(body).toEqual({ user_id: "user_123" });
  expect(getToken).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("https://api.example.test/api/v1/me");
  expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer mock-token");
});

test.each([
  [400, "Allocation exceeds the lot's remaining quantity"],
  [404, "Portfolio not found"],
  [409, "Lot 7 is allocated to sell 3"],
  [500, "Internal Server Error"],
])("a %i response throws an ApiError with the status and detail", async (status, detail) => {
  fetchMock.mockResolvedValue(jsonResponse(status, { detail }));

  const error = await apiFetch("/api/v1/me", getToken).catch((e: unknown) => e);

  expect(error).toBeInstanceOf(ApiError);
  expect((error as ApiError).status).toBe(status);
  expect((error as ApiError).message).toBe(detail);
});
