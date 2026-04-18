// Mirrors backend Pydantic models. Keep in sync with backend/models.py and bridge.py.

export interface ManifestEntry {
  filename: string;
  cid: string;
  size_bytes: number;
  stored_at: string;
}

export interface VaultListResponse {
  entries: ManifestEntry[];
}

export interface VaultStoreResponse {
  cid: string;
  filename: string;
  size_bytes: number;
  stored_at: string;
}

export interface VaultRetrieveResponse {
  filename: string;
  content: string; // base64
  size_bytes: number;
}

export interface LightningBalanceResponse {
  balance_sats: number;
}

export interface RelayStatus {
  url: string;
  connected: boolean;
}

export interface IdentityInfoResponse {
  pubkey_hex: string;
  npub: string;
  relays: RelayStatus[];
  last_broadcast: { event_id: string; kind: number; ts: string } | null;
}

export interface AuditEntry {
  ts: string;
  level?: string;
  logger?: string;
  message?: string;
  action?: string;
  tool?: string;
  input_hash?: string;
  output_hash?: string;
  ok?: boolean;
  error?: string;
}

export interface AuditResponse {
  entries: AuditEntry[];
}

export interface GooseStatusResponse {
  connected: boolean;
  pid: number | null;
  uptime_seconds: number;
  last_tool_call: { tool: string; ts: string } | null;
  total_calls: number;
}

export type SystemState = "healthy" | "warning" | "error" | "disconnected";
