import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { SystemState } from "@/types/api";

const STATE_COLORS: Record<SystemState, string> = {
  healthy: "#00F0FF",
  warning: "#F59E0B",
  error: "#EF4444",
  disconnected: "#6B7280",
};

interface OrbProps {
  systemState: SystemState;
}

function Orb({ systemState }: OrbProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.MeshStandardMaterial>(null);

  const baseGeometry = useMemo(() => new THREE.IcosahedronGeometry(1.4, 48), []);
  const originalPositions = useMemo(() => {
    const pos = baseGeometry.attributes.position.array.slice() as Float32Array;
    return pos;
  }, [baseGeometry]);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (meshRef.current) {
      meshRef.current.rotation.y = t * 0.08;
      meshRef.current.rotation.x = Math.sin(t * 0.15) * 0.1;

      const geo = meshRef.current.geometry as THREE.BufferGeometry;
      const positions = geo.attributes.position.array as Float32Array;
      const amp = systemState === "disconnected" ? 0.01 : 0.06;
      for (let i = 0; i < positions.length; i += 3) {
        const x = originalPositions[i];
        const y = originalPositions[i + 1];
        const z = originalPositions[i + 2];
        const n = Math.sin(x * 2 + t) * Math.cos(y * 2 + t * 0.7) * Math.sin(z * 2 + t * 0.5);
        const scale = 1 + n * amp;
        positions[i] = x * scale;
        positions[i + 1] = y * scale;
        positions[i + 2] = z * scale;
      }
      geo.attributes.position.needsUpdate = true;
      geo.computeVertexNormals();
    }

    if (materialRef.current) {
      const pulse = 0.5 + Math.sin(t * 1.3) * 0.3;
      materialRef.current.emissiveIntensity = systemState === "disconnected" ? 0.1 : pulse;
    }
  });

  const color = STATE_COLORS[systemState];

  return (
    <mesh ref={meshRef} geometry={baseGeometry}>
      <meshStandardMaterial
        ref={materialRef}
        color={color}
        emissive={color}
        emissiveIntensity={0.6}
        roughness={0.2}
        metalness={0.1}
        wireframe={false}
        transparent
        opacity={0.85}
      />
    </mesh>
  );
}

interface StateOrbProps {
  systemState: SystemState;
}

export function StateOrb({ systemState }: StateOrbProps) {
  return (
    <Canvas
      camera={{ position: [0, 0, 4.5], fov: 50 }}
      gl={{ antialias: true, alpha: true }}
      style={{ background: "transparent" }}
    >
      <fog attach="fog" args={["#000000", 3, 9]} />
      <ambientLight intensity={0.4} />
      <pointLight position={[5, 5, 5]} intensity={0.8} />
      <pointLight position={[-5, -5, -5]} intensity={0.3} color={STATE_COLORS[systemState]} />
      <Orb systemState={systemState} />
    </Canvas>
  );
}
