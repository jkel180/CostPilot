import { getSupabaseBrowserClient } from "@/lib/supabase/client";

// NEXT_PUBLIC_* values are inlined at build time: changing them on the host needs a redeploy.
// Fall back to the local API only in development, never silently in a deployed build.
const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : null);

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Options = { method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"; body?: unknown; orgId?: string | null };

/** Call the CostPilot API with the user's Supabase access token and organization context. */
export async function apiFetch<T>(path: string, { method = "GET", body, orgId }: Options = {}): Promise<T> {
  if (!API_URL) {
    throw new ApiError(0, "NEXT_PUBLIC_API_URL is not set for this deployment. Set it on the host and redeploy.");
  }
  const { data } = await getSupabaseBrowserClient().auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiError(401, "Your session has expired. Please sign in again.");

  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (orgId) headers["X-Organization-Id"] = orgId;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Cannot reach the CostPilot API. Check that the backend is running.");
  }
  if (res.status === 204) return undefined as T;
  const payload = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, describeError(payload) ?? `Request failed (${res.status})`);
  return payload as T;
}

function describeError(payload: unknown): string | null {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return null;
  const detail = (payload as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : ""))
      .filter(Boolean)
      .join("; ");
  }
  return null;
}
