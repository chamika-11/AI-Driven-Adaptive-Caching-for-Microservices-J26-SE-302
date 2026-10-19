// ─────────────────────────────────────────────────────────────────────────────
// Reusable API Client — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Centralizes HTTP fetch requests, query serialization, timeout handling,
// and safe error extraction.
// ─────────────────────────────────────────────────────────────────────────────

export interface ApiClientConfig {
  baseUrl?: string;
}

export class ApiError extends Error {
  public readonly statusCode: number;
  public readonly issues?: string[];

  constructor(message: string, statusCode: number, issues?: string[]) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.issues = issues;
  }
}

/**
 * Resolves the backend base URL.
 * In development, defaults to empty string so requests hit the Vite dev proxy (/api).
 * In production or custom environments, uses VITE_API_BASE_URL.
 */
export function getApiBaseUrl(): string {
  const envUrl = import.meta.env["VITE_API_BASE_URL"];
  if (envUrl && typeof envUrl === "string" && envUrl.trim() !== "") {
    return envUrl.trim().replace(/\/+$/, "");
  }
  return "";
}

/**
 * Performs a type-safe HTTP request with standardized error parsing and abort signal support.
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const normalizedEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = `${baseUrl}${normalizedEndpoint}`;

  const headers = new Headers(options.headers || {});
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (error: unknown) {
    if (
      (error instanceof Error && error.name === "AbortError") ||
      (typeof DOMException !== "undefined" &&
        error instanceof DOMException &&
        error.name === "AbortError")
    ) {
      throw error; // Let caller handle component unmount cancellations
    }
    const message = error instanceof Error ? error.message : "Network request failed";
    throw new ApiError(`Unable to connect to the backend API: ${message}`, 0);
  }

  // Handle successful responses
  if (response.ok) {
    if (response.status === 204) {
      return {} as T;
    }
    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError("Failed to parse JSON response from server", response.status);
    }
  }

  // Handle error responses
  let errorMessage = `HTTP Error ${response.status} (${response.statusText})`;
  let issues: string[] | undefined;

  try {
    const errorBody = (await response.json()) as Record<string, unknown>;
    if (typeof errorBody.message === "string") {
      errorMessage = errorBody.message;
    }
    if (Array.isArray(errorBody.issues)) {
      issues = errorBody.issues.map((i) => String(i));
    }
  } catch {
    // If response was not JSON, keep fallback HTTP error message
  }

  throw new ApiError(errorMessage, response.status, issues);
}
