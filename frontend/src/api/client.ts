export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Calls the Findipend API at VITE_API_BASE_URL + path with the Clerk session token.
 * Pass `getToken` from Clerk's `useAuth()`.
 */
export async function apiFetch<T>(
  path: string,
  getToken: () => Promise<string | null>,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = await getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      errorMessage(body?.detail) || `Request failed (${response.status})`,
    );
  }

  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** FastAPI sends `detail` as a string, or for 422 a list of `{loc, msg}` items. */
function errorMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return "";
  return detail
    .filter((item) => typeof item?.msg === "string")
    .map((item) => {
      const field = Array.isArray(item.loc) ? item.loc.at(-1) : undefined;
      return field === undefined ? item.msg : `${field}: ${item.msg}`;
    })
    .join("; ");
}
