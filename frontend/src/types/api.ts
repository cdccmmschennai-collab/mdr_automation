/**
 * Response shapes returned by the backend.
 *
 * These mirror the Pydantic models in `backend/app/api/routes/`. They describe
 * what the API returns; they encode no MDR business rule. When the backend adds
 * a field, add it here — do not compute it on the client.
 */

export interface HealthResponse {
  status: string;
  phase: string;
}

/** `GET /api/mdr/summary`. Kept loose: the backend owns the summary's shape. */
export interface MdrSummaryResponse {
  workbook: string;
  discovery: Record<string, unknown>;
  summary: Record<string, unknown>;
}
