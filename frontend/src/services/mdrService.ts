/**
 * The MDR submission workflow: upload, extract, automate, summary, download.
 * The five `/api/v1/mdr` endpoints Auto MDR's processing and result screens
 * drive.
 */

import { requestBlob, type BlobResponse, request } from './apiClient';
import type { AutomateResponse, ExtractResponse, SummaryResponse, UploadResponse } from '../types/api';

export function uploadWorkbook(plantId: string, file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('plant_id', plantId);
  form.append('mdr_file', file);
  return request<UploadResponse>('/v1/mdr/upload', { method: 'POST', body: form });
}

export function extractSubmission(mdrId: string): Promise<ExtractResponse> {
  return request<ExtractResponse>(`/v1/mdr/${mdrId}/extract`, { method: 'POST' });
}

export function automateSubmission(mdrId: string): Promise<AutomateResponse> {
  return request<AutomateResponse>(`/v1/mdr/${mdrId}/automate`, { method: 'POST' });
}

export function getSummary(mdrId: string): Promise<SummaryResponse> {
  return request<SummaryResponse>(`/v1/mdr/${mdrId}/summary`);
}

export function downloadWorkbook(mdrId: string): Promise<BlobResponse> {
  return requestBlob(`/v1/mdr/${mdrId}/download`);
}
