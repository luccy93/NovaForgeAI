"use client";

import { useRef, useMemo, useEffect, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Float, MeshDistortMaterial } from "@react-three/drei";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import { BlendFunction } from "postprocessing";
import * as THREE from "three";

/**
 * Deterministic PRNG so static scene geometry is stable across renders
 * (and satisfies the react-hooks/purity lint rule for memoized values).
 */
function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state |= 0;
    state = (state + 0x6d2b79f5) | 0;
    let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

function ParticleField({ count = 1200 }) {
  const ref = useRef<THREE.Points>(null!);
  const positions = useMemo(() => {
    const rand = mulberry32(count);
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (rand() - 0.5) * 20;
      pos[i * 3 + 1] = (rand() - 0.5) * 20;
      pos[i * 3 + 2] = (rand() - 0.5) * 20;
    }
    return pos;
  }, [count]);

  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.y = state.clock.elapsedTime * 0.02;
      ref.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.01) * 0.1;
    }
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.04} color="#FFD400" transparent opacity={0.6} sizeAttenuation blending={THREE.AdditiveBlending} depthWrite={false} />
    </points>
  );
}

function NeuralNode({ position, color = "#FFD400" }: { position: [number, number, number]; color?: string }) {
  return (
    <Float speed={1.5} rotationIntensity={0.4} floatIntensity={0.5}>
      <mesh position={position}>
        <icosahedronGeometry args={[0.3, 1]} />
        <MeshDistortMaterial color={color} emissive={color} emissiveIntensity={0.5} roughness={0.2} metalness={0.8} wireframe />
      </mesh>
    </Float>
  );
}

function NeuralConnections() {
  const ref = useRef<THREE.Group>(null!);
  const nodes = useMemo(() => {
    const rand = mulberry32(12);
    const n: [number, number, number][] = [];
    for (let i = 0; i < 12; i++) {
      const theta = (i / 12) * Math.PI * 2;
      const phi = rand() * Math.PI;
      const r = 2.5 + rand() * 1.5;
      n.push([Math.sin(phi) * Math.cos(theta) * r, Math.sin(phi) * Math.sin(theta) * r, Math.cos(phi) * r]);
    }
    return n;
  }, []);

  const lines = useMemo(() => {
    const rand = mulberry32(nodes.length);
    const pairs: [number, number][] = [];
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        if (rand() > 0.7) pairs.push([i, j]);
      }
    }
    return pairs;
  }, [nodes]);

  const linePositions = useMemo(() => {
    const positions: number[] = [];
    lines.forEach(([i, j]) => {
      positions.push(...nodes[i], ...nodes[j]);
    });
    return new Float32Array(positions);
  }, [lines, nodes]);

  useFrame((state) => {
    if (ref.current) ref.current.rotation.y = state.clock.elapsedTime * 0.05;
  });

  return (
    <group ref={ref}>
      {nodes.map((pos, i) => (
        <NeuralNode key={i} position={pos} color={i % 3 === 0 ? "#FFD400" : i % 3 === 1 ? "#FFE177" : "#EBC300"} />
      ))}
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[linePositions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color="#FFD400" transparent opacity={0.15} />
      </lineSegments>
    </group>
  );
}

function CoreGlow() {
  const ref = useRef<THREE.Mesh>(null!);
  useFrame((state) => {
    if (ref.current) {
      ref.current.scale.setScalar(1 + Math.sin(state.clock.elapsedTime * 0.5) * 0.05);
    }
  });

  return (
    <mesh ref={ref}>
      <sphereGeometry args={[0.8, 32, 32]} />
      <MeshDistortMaterial
        color="#FFD400"
        emissive="#FFD400"
        emissiveIntensity={1.5}
        roughness={0.1}
        metalness={0.9}
        distort={0.1}
        speed={2}
      />
    </mesh>
  );
}

function Scene({ mouse }: { mouse: { x: number; y: number } }) {
  const groupRef = useRef<THREE.Group>(null!);
  useFrame(() => {
    if (groupRef.current) {
      groupRef.current.rotation.x = mouse.y * 0.1;
      groupRef.current.rotation.y = mouse.x * 0.1;
    }
  });

  return (
    <>
      <group ref={groupRef}>
        <CoreGlow />
        <NeuralConnections />
        <ParticleField />
      </group>
      <ambientLight intensity={0.2} />
      <directionalLight position={[5, 5, 5]} intensity={1.5} color="#FFD400" />
      <directionalLight position={[-3, -2, 4]} intensity={0.8} color="#FFE177" />
      <pointLight position={[0, 0, 0]} intensity={2} color="#FFD400" distance={10} />
    </>
  );
}

export function AICoreScene({ className }: { className?: string }) {
  const [mouse, setMouse] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      setMouse({ x: (e.clientX / window.innerWidth) * 2 - 1, y: -(e.clientY / window.innerHeight) * 2 + 1 });
    };
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, []);

  return (
    <div className={className}>
      <Canvas camera={{ position: [0, 0, 6], fov: 45 }} dpr={[1, 2]} gl={{ antialias: true, alpha: true }}>
        <Scene mouse={mouse} />
        <OrbitControls enableZoom={false} enablePan={false} enableRotate={false} />
        <EffectComposer>
          <Bloom luminanceThreshold={0.2} luminanceSmoothing={0.9} intensity={0.8} />
          <ChromaticAberration blendFunction={BlendFunction.NORMAL} offset={[0.002, 0.002]} />
        </EffectComposer>
      </Canvas>
    </div>
  );
}
