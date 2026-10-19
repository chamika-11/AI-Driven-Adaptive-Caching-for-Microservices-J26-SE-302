// ─────────────────────────────────────────────────────────────────────────────
// API Documentation Service — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// API client methods for OpenAPI/Swagger document ingestion and endpoint queries.
// ─────────────────────────────────────────────────────────────────────────────

import { apiRequest, getApiBaseUrl } from "./api.client.js";

export interface ParameterMetadata {
  name: string;
  location: string;
  required: boolean;
  description?: string | null;
  schema_type?: string | null;
}

export interface RequestBodyMetadata {
  required: boolean;
  description?: string | null;
  content_types: string[];
  schema_ref?: string | null;
}

export interface ResponseMetadata {
  status_code: string;
  description?: string | null;
  content_types: string[];
  schema_ref?: string | null;
}

export interface NormalizedEndpoint {
  id: string;
  document_id: string;
  service_name: string;
  path: string;
  method: string;
  operation_id?: string | null;
  summary?: string | null;
  description?: string | null;
  tags: string[];
  parameters: ParameterMetadata[];
  request_body?: RequestBodyMetadata | null;
  responses: ResponseMetadata[];
  source_file?: string | null;
  extracted_at: string;
}

export interface DocumentMetadata {
  document_id: string;
  title: string;
  version: string;
  description?: string | null;
  service_name: string;
  spec_format: string;
  spec_version: string;
  base_urls: string[];
  filename?: string | null;
  file_size_bytes: number;
}

export interface IngestionResponse {
  success: boolean;
  message: string;
  document?: DocumentMetadata | null;
  endpoints_count: number;
  endpoints: NormalizedEndpoint[];
  warnings: string[];
  errors: string[];
}

/**
 * Uploads an OpenAPI or Swagger file for validation and endpoint normalization.
 */
export async function uploadSpecification(file: File): Promise<IngestionResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/api/docs/ingest`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      body: formData,
      headers: {
        Accept: "application/json",
      },
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Failed to upload specification: ${msg}`);
  }

  const data = await response.json();
  if (!response.ok) {
    const errorMsg = data.message || `Upload failed with HTTP ${response.status}`;
    throw new Error(errorMsg);
  }

  return data as IngestionResponse;
}

/**
 * Fetches all ingested specifications.
 */
export async function getIngestedDocuments(): Promise<DocumentMetadata[]> {
  return apiRequest<DocumentMetadata[]>("/api/docs/documents");
}

/**
 * Fetches normalized endpoints, optionally filtered by service.
 */
export async function getNormalizedEndpoints(serviceName?: string): Promise<NormalizedEndpoint[]> {
  const query = serviceName ? `?service_name=${encodeURIComponent(serviceName)}` : "";
  return apiRequest<NormalizedEndpoint[]>(`/api/docs/endpoints${query}`);
}
