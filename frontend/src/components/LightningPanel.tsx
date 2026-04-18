import { usePolling } from "@/hooks/usePolling";
import { GlassCard } from "./GlassCard";
import type { LightningBalanceResponse } from "@/types/api";

const ACCENT = "#F59E0B";
const MAX_DAILY_SATS_DEFAULT = 10000;

export function LightningPanel() {
  const { data, stale } = usePolling<LightningBalanceResponse>("/lightning/balance", 3000);
  // Daily spend isn't exposed via the bridge yet — future enhancement. For now
  // we show the balance and a placeholder progress bar bound to 0.
  const dailySpend = 0;
  const pct = Math.min(100, (dailySpend / MAX_DAILY_SATS_DEFAULT) * 100);

  return (
    <GlassCard title="Lightning" accentColor={ACCENT} stale={stale}>
      <div className="flex items-baseline gap-2">
        <div className="text-4xl font-mono" style={{ color: ACCENT }}>
          {data?.balance_sats.toLocaleString() ?? "—"}
        </div>
        <div className="text-xs uppercase tracking-widest text-ink-muted">sats</div>
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-widest text-ink-muted mb-1">
          <span>daily spend</span>
          <span>
            {dailySpend} / {MAX_DAILY_SATS_DEFAULT}
          </span>
        </div>
        <div className="h-1.5 bg-ink-border rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${pct}%`, background: ACCENT }}
          />
        </div>
      </div>

      <div className="mt-3 text-[11px] font-mono text-ink-muted">last payment: —</div>
    </GlassCard>
  );
}
