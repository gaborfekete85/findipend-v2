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

async function apiErrorFor(response: Response) {
  fetchMock.mockResolvedValue(response);
  const error = await apiFetch("/api/v1/portfolios", getToken).catch((e: unknown) => e);
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

test("a 422 validation error names the field and the reason", async () => {
  const error = await apiErrorFor(
    jsonResponse(422, {
      detail: [{ loc: ["body", "name"], msg: "String should have at least 1 character" }],
    }),
  );

  expect(error.status).toBe(422);
  expect(error.message).toBe("name: String should have at least 1 character");
});

test("a 422 with two validation items joins both messages with '; '", async () => {
  const error = await apiErrorFor(
    jsonResponse(422, {
      detail: [
        { loc: ["body", "name"], msg: "String should have at least 1 character" },
        { loc: ["body", "lots", 0, "quantity"], msg: "Input should be greater than 0" },
      ],
    }),
  );

  expect(error.status).toBe(422);
  expect(error.message).toBe(
    "name: String should have at least 1 character; quantity: Input should be greater than 0",
  );
});

test("a 409 with a string detail keeps that message", async () => {
  const error = await apiErrorFor(jsonResponse(409, { detail: "Portfolio name already exists" }));

  expect(error.status).toBe(409);
  expect(error.message).toBe("Portfolio name already exists");
});

test.each([
  ["a non-JSON body", new Response("<html>oops</html>", { status: 500, statusText: "Internal Server Error" })],
  ["an empty body", new Response(null, { status: 500, statusText: "Internal Server Error" })],
  ["JSON without detail", jsonResponse(500, { error: "boom" })],
])("a 500 with %s gives 'Request failed (500)'", async (_label, response) => {
  const error = await apiErrorFor(response);

  expect(error.status).toBe(500);
  expect(error.message).toBe("Request failed (500)");
});

test("a 204 response resolves to undefined without throwing", async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

  await expect(apiFetch("/api/v1/portfolios/1", getToken, { method: "DELETE" })).resolves.toBeUndefined();
});

test("a 200 with an empty body resolves to undefined without throwing", async () => {
  fetchMock.mockResolvedValue(new Response("", { status: 200 }));

  await expect(apiFetch("/api/v1/portfolios/1", getToken)).resolves.toBeUndefined();
});
