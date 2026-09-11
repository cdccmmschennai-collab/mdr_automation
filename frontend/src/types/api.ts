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

/** `mdr_submissions.status` — mirrors `SubmissionStatus` in
 * `backend/app/domain/enums/lifecycle.py`. */
export type SubmissionStatus = 'UPLOADED' | 'EXTRACTED' | 'AUTOMATED' | 'FAILED';

/** `GET /api/v1/plants`. */
export interface PlantResponse {
  id: string;
  code: string;
  name: string;
}

/** `POST /api/v1/mdr/upload`. */
export interface UploadResponse {
  mdr_id: string;
  submission_no: number;
  plant_id: string;
  status: SubmissionStatus;
  source_filename: string;
  source_sha256: string;
  source_byte_size: number;
  uploaded_at: string;
}

/** `POST /api/v1/mdr/{mdr_id}/extract`. */
export interface ExtractResponse {
  mdr_id: string;
  status: SubmissionStatus;
  source_sheet_name: string;
  source_header_row: number | null;
  source_row_count: number | null;
  extracted_at: string | null;
}

export interface RuleSetRef {
  rule_set_id: string;
  version_label: string;
  source_filename: string;
  content_sha256: string;
}

/** `POST /api/v1/mdr/{mdr_id}/automate`. */
export interface AutomateResponse {
  mdr_id: string;
  status: SubmissionStatus;
  row_count: number;
  rule_set: RuleSetRef;
  automated_at: string | null;
}

/** `GET /api/v1/mdr/{mdr_id}/summary`. Mirrors `SummaryResponse` in
 * `backend/app/api/schemas/mdr.py`. Before AUTOMATED the counters are zero,
 * `rule_set` is null and `counts` is empty. */
export interface SummaryResponse {
  mdr_id: string;
  submission_no: number;
  plant_id: string;
  plant_code: string;
  status: SubmissionStatus;
  failure_reason: string;
  source_filename: string;
  uploaded_at: string;
  extracted_at: string | null;
  automated_at: string | null;

  rule_set: RuleSetRef | null;
  engine_version: string;

  row_count: number;
  doc_with_rev_populated: number;
  doc_type_populated: number;
  sow_populated: number;
  sow_unresolved: number;
  idb_populated: number;
  idb_unmapped: number;
  idb_manual_check_required: number;
  check_status_populated: number;

  counts: Record<string, unknown>;
}
