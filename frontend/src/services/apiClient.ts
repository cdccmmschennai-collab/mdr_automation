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
      (await readErrorDetail(response)) ??
        `${init?.method ?? 'GET'} ${path} failed: ${response.status} ${response.statusText}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}

/** FastAPI's error body is `{ detail: string }` — client-safe by contract
 * (see `WorkflowError` on the backend), so it is what the user sees. */
async function readErrorDetail(response: Response): Promise<string | undefined> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      return body.detail;
    }
    return undefined;
  } catch {
    return undefined;
  }
}

export interface BlobResponse {
  blob: Blob;
  /** From `Content-Disposition`, when the backend sent one. */
  filename?: string;
}

/** Filename out of a `Content-Disposition: attachment; filename="..."` (or
 * unquoted) header value. */
function filenameFromContentDisposition(header: string | null): string | undefined {
  if (!header) return undefined;
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
  return match?.[1] ? decodeURIComponent(match[1]) : undefined;
}

/** For endpoints that answer with a file rather than JSON — the download
 * endpoint's xlsx byte stream. Errors still come back as `{ detail }` JSON,
 * same as `request`. */
export async function requestBlob(path: string, init?: RequestInit): Promise<BlobResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch (cause) {
    throw new ApiError(`could not reach the backend at ${BASE_URL}${path}`, 0);
  }

  if (!response.ok) {
    throw new ApiError(
      (await readErrorDetail(response)) ??
        `${init?.method ?? 'GET'} ${path} failed: ${response.status} ${response.statusText}`,
      response.status,
    );
  }
  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get('Content-Disposition')),
  };
}
