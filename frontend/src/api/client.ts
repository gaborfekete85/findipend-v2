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
    const detail = typeof body?.detail === "string" ? body.detail : response.statusText;
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}
