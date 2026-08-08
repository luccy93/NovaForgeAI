"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { fadeUp, staggerContainer } from "@/lib/animations";
import { ArrowRight } from "lucide-react";

const capabilities = [
  {
    num: "01",
    title: "Independent transforms",
    description: "Animate x, y, rotate, scale on the same element, without wrappers.",
    active: false,
    illustration: (
      <svg width="100%" height="100%" viewBox="0 0 100 100" fill="none" className="w-full h-full max-h-[160px]">
        <rect x="30" y="30" width="40" height="40" stroke="currentColor" strokeWidth="1" strokeDasharray="4 4" className="text-white/20" />
        <rect x="35" y="35" width="30" height="30" fill="#FFED00" transform="rotate(15 50 50)" />
      </svg>
    )
  },
  {
    num: "02",
    title: "Scroll animation",
    description: "Hardware-accelerated scroll-linked motion via ScrollTimeline.",
    active: true,
    illustration: (
      <svg width="100%" height="100%" viewBox="0 0 100 100" fill="none" className="w-full h-full max-h-[160px]">
        <circle cx="50" cy="50" r="40" stroke="currentColor" strokeWidth="1" strokeDasharray="4 4" className="text-black/30" />
        <circle cx="50" cy="50" r="30" stroke="currentColor" strokeWidth="1.5" className="text-black" />
        <circle cx="50" cy="50" r="16" fill="transparent" stroke="currentColor" strokeWidth="1" className="text-black" />
        <circle cx="36" cy="18" r="3" fill="currentColor" className="text-black" />
      </svg>
    )
  },
  {
    num: "03",
    title: "Native gestures",
    description: "hover, press, and drag that feel native, not bolted on.",
    active: false,
    illustration: (
      <svg width="100%" height="100%" viewBox="0 0 100 100" fill="none" className="w-full h-full max-h-[160px]">
        <rect x="15" y="15" width="70" height="70" stroke="currentColor" strokeWidth="1" strokeDasharray="2 2" className="text-primary-container" />
        <rect x="40" y="40" width="20" height="20" fill="rgba(255, 237, 0, 0.15)" stroke="currentColor" strokeWidth="1" className="text-primary-container" />
      </svg>
    )
  },
  {
    num: "04",
    title: "Layout animation",
    description: "Animate between any two layouts with a single layout prop.",
    active: false,
    illustration: (
      <svg width="100%" height="100%" viewBox="0 0 100 100" fill="none" className="w-full h-full max-h-[160px]">
        <rect x="25" y="25" width="22" height="22" fill="#EAEAEA" />
        <rect x="53" y="25" width="22" height="22" fill="#EAEAEA" />
        <rect x="25" y="53" width="22" height="22" fill="#EAEAEA" />
        <rect x="53" y="53" width="22" height="22" fill="#EAEAEA" />
      </svg>
    )
  }
];

export function CapabilitiesSection() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const opacity = useTransform(scrollYProgress, [0, 0.2], [0, 1]);

  return (
    <section id="capabilities" ref={ref} className="relative bg-[#0f0f0f] border-t border-white/10">
      <motion.div style={{ opacity }} className="w-full">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-white/10">
          {capabilities.map((cap) => (
            <motion.div 
              key={cap.num} 
              variants={fadeUp} 
              initial="hidden" 
              whileInView="visible" 
              viewport={{ once: true }}
              className={`flex flex-col h-full group ${cap.active ? "bg-primary-container" : "bg-[#0f0f0f] hover:bg-[#151515]"} transition-colors`}
            >
              {/* Illustration Area */}
              <div className="relative h-[250px] sm:h-[300px] flex items-center justify-center p-8 border-b border-white/10">
                {/* Background grid lines similar to Image 1 */}
                <div className={`absolute inset-0 bg-[linear-gradient(to_right,#ffffff0a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff0a_1px,transparent_1px)] bg-[size:50%_50%] pointer-events-none ${cap.active ? "opacity-0" : "opacity-100"}`} />
                {cap.illustration}
              </div>
              
              {/* Text Area */}
              <div className="p-8 flex-1 flex flex-col relative">
                <div className={`font-mono text-sm font-bold tracking-widest mb-6 ${cap.active ? "text-black" : "text-primary-container"}`}>
                  {cap.num}
                </div>
                
                <h3 className={`text-2xl font-bold tracking-tight mb-4 ${cap.active ? "text-black" : "text-white"}`}>
                  {cap.title}
                </h3>
                
                <p className={`text-sm leading-relaxed mb-8 flex-1 ${cap.active ? "text-black/80" : "text-white/60"}`}>
                  {cap.description}
                </p>

                <div className="flex justify-end absolute right-8 bottom-8">
                  <ArrowRight className={`h-4 w-4 transition-transform group-hover:translate-x-1 ${cap.active ? "text-black" : "text-white/40"}`} />
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </section>
  );
}
