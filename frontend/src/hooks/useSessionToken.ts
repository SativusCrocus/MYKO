import { useEffect, useRef, useState } from "react";
import { loadSessionToken } from "@/api/bridge";

export function useSessionToken(): {
  ready: boolean;
  error: string | null;
} {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fired = useRef(false);

  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    loadSessionToken()
      .then(() => setReady(true))
      .catch((err) => setError(String(err)));
  }, []);

  return { ready, error };
}
