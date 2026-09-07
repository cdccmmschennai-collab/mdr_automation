/**
 * The single point through which the frontend talks to the backend.
 *
 * Every network call goes through `request`. Nothing else in the frontend
 * calls `fetch` directly, and nothing here interprets MDR data — it moves
 * JSON across the boundary and nothing more.
 */

/** Relative, so the Vite dev proxy and a production reverse proxy both work. */
const BASE_URL = '/api';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { Accept: 'application/json' },
      ...init,
    });
  } catch (cause) {
    throw new ApiError(`could not reach the backend at ${BASE_URL}${path}`, 0);
  }

  if (!response.ok) {
    throw new ApiError(
      `${init?.method ?? 'GET'} ${path} failed: ${response.status} ${response.statusText}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}
