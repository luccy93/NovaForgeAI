"use client";

import { motion } from "framer-motion";
import { useEffect, useRef } from "react";
import { ArrowRight } from "lucide-react";

function AsciiBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let w = (canvas.width = window.innerWidth);
    let h = (canvas.height = window.innerHeight);

    const resize = () => {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", resize);

    const chars = ["/", "\\", "=", "+", "-", "|", "*"];
    
    const getGradientColor = (nx: number, ny: number) => {
      if (nx < 0.25) return [255, 255, 255, 0.4];
      
      const t = (nx - 0.25) / 0.75; 
      
      let r, g, b;
      if (t < 0.3) {
          const p = t / 0.3;
          r = 0; g = 255 - 155 * p; b = 255;
      } else if (t < 0.6) {
          const p = (t - 0.3) / 0.3;
          r = 255 * p; g = 100 - 100 * p; b = 255;
      } else {
          const p = (t - 0.6) / 0.4;
          r = 255; g = 0 + 80 * p; b = 255 - 255 * p;
      }
      
      const vOffset = Math.sin(ny * Math.PI) * 30;
      r = Math.max(0, Math.min(255, r + vOffset));
      g = Math.max(0, Math.min(255, g + vOffset));
      
      return [r, g, b, 0.9];
    };

    const draw = () => {
      ctx.clearRect(0, 0, w, h);

      const step = 14;
      ctx.font = "12px monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      for (let x = 0; x < w; x += step) {
        for (let y = 0; y < h; y += step) {
          const nx = x / w;
          const ny = y / h;
          
          const noise = Math.sin(x * 0.005) * Math.cos(y * 0.005) + Math.sin(x * 0.01 + y * 0.01);
          const charIndex = Math.floor(Math.abs(noise) * 10) % chars.length;
          const char = chars[charIndex];

          const [r, g, b, a] = getGradientColor(nx, ny);

          ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${a})`;
          ctx.fillText(char, x, y);
        }
      }
    };

    draw();

    return () => {
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 z-0 pointer-events-none" />;
}

function TSIcon() {
  return (
    <div className="w-3.5 h-3.5 bg-[#3178C6] flex items-end justify-end p-[1px] rounded-[1px]">
      <span className="text-[7px] font-sans font-bold text-white leading-none pb-[1px]">TS</span>
    </div>
  );
}

function PythonIcon() {
  return (
    <div className="w-3.5 h-3.5 flex flex-col rounded-[1px] overflow-hidden">
      <div className="w-full h-1/2 bg-[#3776AB]" />
      <div className="w-full h-1/2 bg-[#FFD43B]" />
    </div>
  );
}

function GoIcon() {
  return (
    <div className="w-3.5 h-3.5 bg-[#00ADD8] flex items-center justify-center rounded-full">
      <span className="text-[7px] font-sans font-bold text-white leading-none tracking-tighter">GO</span>
    </div>
  );
}

export function HeroSection() {
  return (
    <section className="relative min-h-[90vh] flex items-center overflow-hidden bg-primary-container pt-20">
      <AsciiBackground />
      
      <div className="mx-auto w-full max-w-[1400px] px-6 lg:px-12 relative z-10 flex items-center h-full">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.7, ease: [0.25, 0.1, 0, 1] }}
          className="bg-[#0f0f0f] text-white p-10 md:p-16 max-w-[650px] w-full border border-white/5 shadow-2xl relative"
        >
          <div className="flex justify-between items-center text-[10px] sm:text-xs font-mono text-white/50 mb-10 tracking-[0.1em] uppercase">
            <span>Open Source / MIT License</span>
            <span>V2.0.1</span>
          </div>

          <h1 className="text-[clamp(44px,5.5vw,72px)] font-bold leading-[1.05] tracking-[-0.04em] mb-10">
            <span className="text-primary-container">NovaForge.</span>
            <br />
            Spatial intelligence
            <br />
            for your codebase.
          </h1>

          <div className="flex items-center gap-8 mb-12">
            <a
              href="#"
              className="inline-flex items-center gap-3 bg-primary-container text-black px-7 py-3.5 text-sm font-bold tracking-[0.1em] uppercase hover:bg-white transition-colors group"
            >
              Get Started <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
            </a>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6 text-xs font-mono text-white/50 tracking-[0.1em]">
            <span className="text-primary-container">{">"}</span>
            <span className="uppercase">Supports</span>
            <div className="flex items-center gap-5 text-white/90">
              <span className="flex items-center gap-2 hover:text-white cursor-pointer transition-colors"><TSIcon /> TYPESCRIPT</span>
              <span className="flex items-center gap-2 hover:text-white cursor-pointer transition-colors"><PythonIcon /> PYTHON</span>
              <span className="flex items-center gap-2 hover:text-white cursor-pointer transition-colors"><GoIcon /> GO</span>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
