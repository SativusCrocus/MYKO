import { useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { GlassCard } from "./GlassCard";
import type { IdentityInfoResponse } from "@/types/api";

const ACCENT = "#A855F7";

function truncateMiddle(s: string, keep = 8): string {
  if (!s || s.length <= keep * 2 + 3) return s;
  return `${s.slice(0, keep)}…${s.slice(-keep)}`;
}

export function IdentityPanel() {
  const { data, stale } = usePolling<IdentityInfoResponse>("/identity/info", 2000);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (!data?.npub) return;
    try {
      await navigator.clipboard.writeText(data.npub);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore clipboard failure */
    }
  };

  return (
    <GlassCard title="Identity" accentColor={ACCENT} stale={stale}>
      <button
        onClick={copy}
        className="w-full text-left"
        title={data?.npub ?? ""}
        style={{ cursor: data?.npub ? "pointer" : "default" }}
      >
        <div className="text-sm font-mono break-all" style={{ color: ACCENT }}>
          {data ? truncateMiddle(data.npub, 10) : "—"}
        </div>
        <div className="text-[10px] uppercase tracking-widest text-ink-muted mt-1">
          {copied ? "copied!" : "click to copy npub"}
        </div>
      </button>

      <div className="mt-4">
        <div className="text-[10px] uppercase tracking-widest text-ink-muted mb-2">relays</div>
        <div className="flex gap-2 flex-wrap">
          {(data?.relays ?? []).map((r) => (
            <div
              key={r.url}
              className="flex items-center gap-1.5 text-[11px] font-mono"
              title={r.url}
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{ background: r.connected ? "#22C55E" : "#6B7280" }}
              />
              <span className="text-ink-muted truncate max-w-[120px]">
                {r.url.replace(/^wss?:\/\//, "")}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 text-[11px] font-mono text-ink-muted">
        last broadcast:{" "}
        {data?.last_broadcast
          ? `kind:${data.last_broadcast.kind}`
          : "none"}
      </div>
    </GlassCard>
  );
}
