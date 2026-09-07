/** Health endpoint. Exists to prove the API boundary works end to end. */

import { request } from './apiClient';
import type { HealthResponse } from '../types/api';

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}
