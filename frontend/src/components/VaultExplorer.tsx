import { useMemo, useRef, useState, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Link } from "react-router-dom";
import * as THREE from "three";
import { usePolling } from "@/hooks/usePolling";
import { apiFetch } from "@/api/bridge";
import { GlassCard } from "./GlassCard";
import type {
  ManifestEntry,
  VaultListResponse,
  VaultRetrieveResponse,
} from "@/types/api";

interface GraphNode {
  entry: ManifestEntry;
  position: THREE.Vector3;
  velocity: THREE.Vector3;
  radius: number;
}

function buildInitialLayout(entries: ManifestEntry[]): GraphNode[] {
  // Deterministic placement on a sphere (Fibonacci lattice), size by bytes.
  const n = entries.length;
  const nodes: GraphNode[] = [];
  const phi = Math.PI * (3 - Math.sqrt(5));
  const maxBytes = Math.max(1, ...entries.map((e) => e.size_bytes));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / Math.max(n - 1, 1)) * 2;
    const radiusAtY = Math.sqrt(1 - y * y);
    const theta = phi * i;
    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;
    const R = 2.5;
    const node: GraphNode = {
      entry: entries[i],
      position: new THREE.Vector3(x * R, y * R, z * R),
      velocity: new THREE.Vector3(),
      radius: 0.08 + 0.25 * (entries[i].size_bytes / maxBytes),
    };
    nodes.push(node);
  }
  return nodes;
}

interface GraphProps {
  entries: ManifestEntry[];
  onSelect: (e: ManifestEntry) => void;
}

function Graph({ entries, onSelect }: GraphProps) {
  const group = useRef<THREE.Group>(null);
  const nodes = useMemo(() => buildInitialLayout(entries), [entries]);

  useFrame(({ clock }) => {
    if (group.current) {
      group.current.rotation.y = clock.getElapsedTime() * 0.05;
    }
    // Simple repulsion step so nodes don't overlap visually.
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const delta = nodes[i].position.clone().sub(nodes[j].position);
        const dist = Math.max(delta.length(), 0.01);
        const target = nodes[i].radius + nodes[j].radius + 0.2;
        if (dist < target) {
          const force = delta.normalize().multiplyScalar((target - dist) * 0.01);
          nodes[i].position.add(force);
          nodes[j].position.sub(force);
        }
      }
    }
  });

  return (
    <group ref={group}>
      {nodes.map((n) => (
        <mesh
          key={n.entry.cid}
          position={n.position}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(n.entry);
          }}
          onPointerOver={(e) => {
            e.stopPropagation();
            document.body.style.cursor = "pointer";
          }}
          onPointerOut={() => {
            document.body.style.cursor = "default";
          }}
        >
          <sphereGeometry args={[n.radius, 24, 24]} />
          <meshStandardMaterial
            color="#00F0FF"
            emissive="#00F0FF"
            emissiveIntensity={0.5}
            roughness={0.3}
          />
        </mesh>
      ))}
    </group>
  );
}

interface DetailPaneProps {
  entry: ManifestEntry | null;
  onClose: () => void;
}

function DetailPane({ entry, onClose }: DetailPaneProps) {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [sizeRetrieved, setSizeRetrieved] = useState<number | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    setStatus("idle");
    setSizeRetrieved(null);
    setError("");
  }, [entry?.cid]);

  if (!entry) return null;

  const retrieve = async () => {
    setStatus("loading");
    try {
      const resp = await apiFetch<VaultRetrieveResponse>("/vault/retrieve", {
        method: "POST",
        body: JSON.stringify({ cid: entry.cid }),
      });
      setSizeRetrieved(resp.size_bytes);
      setStatus("done");
    } catch (err) {
      setError(String(err));
      setStatus("error");
    }
  };

  return (
    <div
      className="absolute top-0 right-0 w-96 h-full p-6 glass z-20 overflow-y-auto"
      style={{ borderRadius: "0 0 0 16px" }}
    >
      <button
        onClick={onClose}
        className="absolute top-3 right-3 text-ink-muted hover:text-ink-fg text-xl"
        aria-label="Close"
      >
        ×
      </button>
      <h3 className="text-sm uppercase tracking-widest text-accent-vault font-mono mb-4">
        {entry.filename}
      </h3>
      <dl className="text-xs font-mono space-y-2">
        <div>
          <dt className="text-ink-muted uppercase text-[10px] tracking-widest">cid</dt>
          <dd className="break-all" style={{ color: "#00F0FF" }}>
            {entry.cid}
          </dd>
        </div>
        <div>
          <dt className="text-ink-muted uppercase text-[10px] tracking-widest">size</dt>
          <dd>{entry.size_bytes.toLocaleString()} bytes</dd>
        </div>
        <div>
          <dt className="text-ink-muted uppercase text-[10px] tracking-widest">stored at</dt>
          <dd>{new Date(entry.stored_at).toLocaleString()}</dd>
        </div>
      </dl>

      <button
        onClick={retrieve}
        disabled={status === "loading"}
        className="mt-6 px-4 py-2 rounded-lg text-xs uppercase tracking-widest font-mono disabled:opacity-50"
        style={{ background: "rgba(0,240,255,0.15)", color: "#00F0FF", border: "1px solid #00F0FF" }}
      >
        {status === "loading" ? "retrieving…" : "retrieve & decrypt"}
      </button>
      {status === "done" && (
        <div className="mt-3 text-[11px] font-mono text-accent-ok">
          ok — {sizeRetrieved} bytes decrypted locally
        </div>
      )}
      {status === "error" && (
        <div className="mt-3 text-[11px] font-mono text-accent-err break-words">
          {error}
        </div>
      )}
    </div>
  );
}

export function VaultExplorer() {
  const { data, stale } = usePolling<VaultListResponse>("/vault/list", 3000);
  const [selected, setSelected] = useState<ManifestEntry | null>(null);
  const entries = data?.entries ?? [];

  return (
    <div className="relative w-full h-full">
      <div className="absolute top-4 left-4 z-10">
        <GlassCard title="Vault Explorer" accentColor="#00F0FF" stale={stale}>
          <div className="text-xs font-mono text-ink-muted">
            {entries.length} CIDs · click a node to inspect
          </div>
          <Link
            to="/"
            className="mt-2 inline-block text-[11px] uppercase tracking-widest font-mono"
            style={{ color: "#00F0FF" }}
          >
            ← back
          </Link>
        </GlassCard>
      </div>

      <Canvas camera={{ position: [0, 0, 7], fov: 55 }} gl={{ antialias: true, alpha: true }}>
        <ambientLight intensity={0.4} />
        <pointLight position={[5, 5, 5]} intensity={0.7} color="#00F0FF" />
        <pointLight position={[-5, -5, -5]} intensity={0.3} />
        <Graph entries={entries} onSelect={setSelected} />
      </Canvas>

      <DetailPane entry={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
