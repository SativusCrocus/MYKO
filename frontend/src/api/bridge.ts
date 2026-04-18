// Typed fetch wrapper for the localhost FastAPI bridge.
// Reads the session token from ~/MYKO/.session_token via the Tauri fs plugin
// (falls back to a no-op in browser dev) and attaches Bearer auth.

import { readTextFile, BaseDirectory } from "@tauri-apps/plugin-fs";

export const API_BASE = "http://127.0.0.1:9473";

let cachedToken: string | null = null;

export async function loadSessionToken(): Promise<string> {
  if (cachedToken) return cachedToken;
  try {
    // Tauri 2 fs plugin: read from ~/MYKO/.session_token
    const raw = await readTextFile("MYKO/.session_token", {
      baseDir: BaseDirectory.Home,
    });
    cachedToken = raw.trim();
    return cachedToken;
  } catch (err) {
    // Dev-time fallback: some setups put the token in localStorage for browser preview.
    const fallback = typeof localStorage !== "undefined" ? localStorage.getItem("myko_token") : null;
    if (fallback) {
      cachedToken = fallback;
      return fallback;
    }
    throw new Error(`Could not read session token: ${String(err)}`);
  }
}

// Per-endpoint "last good" cache so a transient fetch error doesn't blank the UI.
const lastGood = new Map<string, unknown>();

export class BridgeError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await loadSessionToken();
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const url = `${API_BASE}${path}`;
  try {
    const resp = await fetch(url, { ...options, headers });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new BridgeError(`${resp.status} ${resp.statusText} ${text}`.trim(), resp.status);
    }
    const data = (await resp.json()) as T;
    lastGood.set(path, data);
    return data;
  } catch (err) {
    const cached = lastGood.get(path);
    if (cached !== undefined) {
      // Re-throw but caller's usePolling can fall back to cached — we also return it via second path.
      const wrapped = new BridgeError(`Fetch failed; returning cached value: ${String(err)}`);
      (wrapped as BridgeError & { cached?: unknown }).cached = cached;
      throw wrapped;
    }
    throw err;
  }
}

export function getCached<T>(path: string): T | undefined {
  return lastGood.get(path) as T | undefined;
}
