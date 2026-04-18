import { usePolling } from "@/hooks/usePolling";
import { GlassCard } from "./GlassCard";
import type { GooseStatusResponse } from "@/types/api";

const ACCENT = "#3B82F6";

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatRelative(ts: string | undefined | null): string {
  if (!ts) return "—";
  const then = new Date(ts).getTime();
  if (isNaN(then)) return ts;
  const delta = Math.floor((Date.now() - then) / 1000);
  if (delta < 5) return "just now";
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  return `${Math.floor(delta / 3600)}h ago`;
}

export function GooseStatus() {
  const { data, stale } = usePolling<GooseStatusResponse>("/goose/status", 2000);
  const connected = Boolean(data?.connected);

  return (
    <GlassCard title="Goose ★ MCP Brain" accentColor={ACCENT} stale={stale}>
      <div className="flex items-center gap-3 mb-4">
        <span
          className={`w-3 h-3 rounded-full ${connected ? "pulse-glow" : ""}`}
          style={{ background: connected ? ACCENT : "#6B7280" }}
        />
        <span className="text-sm font-mono uppercase tracking-wider" style={{ color: connected ? ACCENT : "#6B7280" }}>
          {connected ? "connected" : "disconnected"}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-2 text-xs font-mono">
        <dt className="text-ink-muted">pid</dt>
        <dd>{data?.pid ?? "—"}</dd>
        <dt className="text-ink-muted">uptime</dt>
        <dd>{data ? formatUptime(data.uptime_seconds) : "—"}</dd>
        <dt className="text-ink-muted">calls</dt>
        <dd>{data?.total_calls ?? 0}</dd>
        <dt className="text-ink-muted">last tool</dt>
        <dd className="truncate">{data?.last_tool_call?.tool ?? "—"}</dd>
        <dt className="text-ink-muted">at</dt>
        <dd>{formatRelative(data?.last_tool_call?.ts ?? null)}</dd>
      </dl>
    </GlassCard>
  );
}
