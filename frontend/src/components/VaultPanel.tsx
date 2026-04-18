import { Link } from "react-router-dom";
import { usePolling } from "@/hooks/usePolling";
import { GlassCard } from "./GlassCard";
import type { VaultListResponse } from "@/types/api";

const ACCENT = "#00F0FF";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MiB`;
}

export function VaultPanel() {
  const { data, stale } = usePolling<VaultListResponse>("/vault/list", 2000);
  const entries = data?.entries ?? [];
  const total = entries.reduce((acc, e) => acc + e.size_bytes, 0);
  const last = entries[entries.length - 1];

  return (
    <GlassCard title="Vault" accentColor={ACCENT} stale={stale}>
      <div className="flex items-baseline gap-4 mb-3">
        <div>
          <div className="text-3xl font-mono" style={{ color: ACCENT }}>
            {entries.length}
          </div>
          <div className="text-[10px] uppercase tracking-widest text-ink-muted">files</div>
        </div>
        <div>
          <div className="text-xl font-mono text-ink-fg">{formatBytes(total)}</div>
          <div className="text-[10px] uppercase tracking-widest text-ink-muted">pinned</div>
        </div>
      </div>
      <div className="text-xs font-mono text-ink-muted">
        <div>last: {last?.filename ?? "—"}</div>
        <div className="truncate opacity-60">{last?.cid ?? ""}</div>
      </div>
      <Link
        to="/vault"
        className="mt-4 inline-block text-[11px] font-mono uppercase tracking-widest"
        style={{ color: ACCENT }}
      >
        open explorer →
      </Link>
    </GlassCard>
  );
}
