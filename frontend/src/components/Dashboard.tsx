import { useMemo } from "react";
import { usePolling } from "@/hooks/usePolling";
import { StateOrb } from "./StateOrb";
import { GooseStatus } from "./GooseStatus";
import { VaultPanel } from "./VaultPanel";
import { IdentityPanel } from "./IdentityPanel";
import { LightningPanel } from "./LightningPanel";
import { AuditFeed } from "./AuditFeed";
import type { GooseStatusResponse, LightningBalanceResponse, SystemState } from "@/types/api";

export function Dashboard() {
  // The orb colour is derived from whatever the polling layer has for Goose + Lightning.
  const { data: goose, error: gooseErr } = usePolling<GooseStatusResponse>("/goose/status", 2000);
  const { error: lnErr } = usePolling<LightningBalanceResponse>("/lightning/balance", 4000);

  const systemState: SystemState = useMemo(() => {
    if (gooseErr && lnErr) return "error";
    if (!goose?.connected) return "disconnected";
    if (lnErr) return "warning";
    return "healthy";
  }, [goose?.connected, gooseErr, lnErr]);

  return (
    <div className="relative w-full h-full p-6">
      {/* Orb fills the center */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-[40%] h-[40%] min-w-[300px] min-h-[300px]">
          <StateOrb systemState={systemState} />
        </div>
      </div>

      {/* Panels grid (fixed positions, z above orb) */}
      <div className="relative grid grid-cols-3 grid-rows-3 gap-6 w-full h-full z-10 pointer-events-none">
        <div className="pointer-events-auto">
          <VaultPanel />
        </div>
        <div className="pointer-events-auto">
          <GooseStatus />
        </div>
        <div className="pointer-events-auto">
          <IdentityPanel />
        </div>

        <div />
        <div />
        <div />

        <div className="pointer-events-auto">
          <LightningPanel />
        </div>
        <div />
        <div className="pointer-events-auto">
          <AuditFeed />
        </div>
      </div>
    </div>
  );
}
