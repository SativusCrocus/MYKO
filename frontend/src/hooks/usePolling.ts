import { useEffect, useRef, useState } from "react";
import { apiFetch, getCached } from "@/api/bridge";

export interface PollingResult<T> {
  data: T | null;
  stale: boolean;
  error: string | null;
}

export function usePolling<T>(path: string, intervalMs: number): PollingResult<T> {
  const [data, setData] = useState<T | null>(() => getCached<T>(path) ?? null);
  const [stale, setStale] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const next = await apiFetch<T>(path);
        if (!mounted.current) return;
        setData(next);
        setStale(false);
        setError(null);
      } catch (err) {
        if (!mounted.current) return;
        const cached = getCached<T>(path);
        if (cached !== undefined) {
          setData(cached);
          setStale(true);
        }
        setError(String(err));
      } finally {
        if (mounted.current) {
          timer = setTimeout(tick, intervalMs);
        }
      }
    };

    tick();
    return () => {
      mounted.current = false;
      if (timer) clearTimeout(timer);
    };
  }, [path, intervalMs]);

  return { data, stale, error };
}
