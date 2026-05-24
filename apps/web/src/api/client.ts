/** Dev: empty VITE_API_URL → same-origin `/api/...` + Vite proxy (avoids CORS). Prod: full URL required. */
const rawBase = (import.meta.env.VITE_API_URL as string | undefined)?.trim().replace(/\/$/, "") ?? "";
const useDevProxy = Boolean(import.meta.env.DEV && !rawBase);

export function apiUrl(path: string) {
  const p = path.startsWith("/") ? path : `/${path}`;
  if (useDevProxy) return `/api${p}`;
  if (!rawBase) {
    throw new Error("Set VITE_API_URL for production builds (e.g. https://your-api.onrender.com)");
  }
  return `${rawBase}${p}`;
}

export async function apiFetch<T>(
  path: string,
  opts: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const headers = new Headers(opts.headers);
  if (opts.body && !(opts.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (opts.token) headers.set("Authorization", `Bearer ${opts.token}`);
  const { token: _t, ...rest } = opts;
  const res = await fetch(apiUrl(path), { ...rest, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (j?.detail !== undefined) {
        if (typeof j.detail === "string") detail = j.detail;
        else if (Array.isArray(j.detail))
          detail = j.detail
            .map((e: { msg?: string; loc?: unknown[] }) => {
              const loc = Array.isArray(e?.loc) ? e.loc.join(".") : "";
              return loc ? `${loc}: ${e?.msg ?? JSON.stringify(e)}` : e?.msg ?? JSON.stringify(e);
            })
            .join("; ");
        else detail = JSON.stringify(j.detail);
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
