/** Plants a submission can belong to. Read-only: `GET /api/v1/plants`. */

import { request } from './apiClient';
import type { PlantResponse } from '../types/api';

export function listPlants(): Promise<PlantResponse[]> {
  return request<PlantResponse[]>('/v1/plants');
}
