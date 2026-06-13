/**
 * Typed client for the Ayanakoji backend.
 *
 * Base URL comes from NEXT_PUBLIC_API_BASE_URL (exposed to the browser) and
 * defaults to the local FastAPI dev server. No secrets here — public config only.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface PingResponse {
  message: string;
  service: string;
  version: string;
  timestamp: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

/** Call the backend connectivity endpoint. Throws on non-2xx or network failure. */
export async function pingBackend(
  signal?: AbortSignal,
): Promise<PingResponse> {
  const response = await fetch(`${API_BASE_URL}/api/ping`, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Backend ping failed: ${response.status}`);
  }

  return (await response.json()) as PingResponse;
}
