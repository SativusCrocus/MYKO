import { useEffect, useRef } from "react";
import { usePolling } from "@/hooks/usePolling";
import { GlassCard } from "./GlassCard";
import type { AuditEntry, AuditResponse } from "@/types/api";

const TOOL_COLORS: Record<string, string> = {
  vault_store: "#00F0FF",
  vault_retrieve: "#00F0FF",
  vault_list: "#00F0FF",
  ipfs_pin_directory: "#00F0FF",
  nostr_broadcast: "#A855F7",
  nostr_encrypt_dm: "#A855F7",
  lightning_balance: "#F59E0B",
  lightning_create_invoice: "#F59E0B",
  lightning_pay: "#F59E0B",
};

function tsShort(ts: string): string {
  // Accepts ISO8601 or the audit formatter's date string. Show HH:MM:SS.
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString("en-GB", { hour12: false });
}

function entryKey(e: AuditEntry, i: number): string {
  return `${e.ts}-${e.tool ?? e.action ?? "event"}-${i}`;
}

export function AuditFeed() {
  const { data, stale } = usePolling<AuditResponse>("/audit/recent?limit=50", 2000);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const entries = data?.entries ?? [];

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries.length]);

  return (
    <GlassCard title="Audit Feed" accentColor="#FFFFFF" stale={stale}>
      <div
        ref={scrollRef}
        className="h-48 overflow-y-auto pr-1 text-[11px] font-mono space-y-1"
      >
        {entries.length === 0 && <div className="text-ink-muted">no events yet</div>}
        {entries.map((e, i) => {
          const tool = e.tool ?? "";
          const color = TOOL_COLORS[tool] ?? "#6B7280";
          const ok = e.ok;
          const dotColor =
            ok === true ? "#22C55E" : ok === false ? "#EF4444" : "#6B7280";
          return (
            <div key={entryKey(e, i)} className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: dotColor }} />
              <span className="text-ink-muted">{tsShort(e.ts)}</span>
              {tool && (
                <span
                  className="px-1.5 py-0.5 rounded text-[10px]"
                  style={{
                    color,
                    border: `1px solid ${color}33`,
                    background: `${color}11`,
                  }}
                >
                  {tool}
                </span>
              )}
              <span className="truncate text-ink-fg/80">
                {e.action ?? e.message ?? ""}
              </span>
              {e.error && (
                <span className="text-red-400 truncate text-[10px]">{e.error}</span>
              )}
            </div>
          );
        })}
      </div>
    </GlassCard>
  );
}
