"use client";

import React, { memo } from "react";
import { EdgeProps, getBezierPath, BaseEdge } from "reactflow";
import { motion, AnimatePresence } from "framer-motion";

export const AnimatedEdge = memo(({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  data,
  markerEnd,
}: EdgeProps) => {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const isActive = data?.isActive;
  const color = data?.color || "rgb(99 102 241)"; // default indigo-500

  return (
    <>
      {/* Base Path (Shadow/Depth) */}
      <BaseEdge
        path={edgePath}
        style={{
          ...style,
          strokeWidth: isActive ? 4 : 2,
          stroke: "rgb(148 163 184)", // slate-400
          opacity: 0.1,
          transition: "stroke-width 0.8s, opacity 0.8s",
        }}
      />

      {/* Main Flow Path */}
      <BaseEdge
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...style,
          strokeWidth: isActive ? 2.5 : 1,
          stroke: isActive ? color : "rgb(203 213 225)", // slate-300
          opacity: isActive ? 1 : 0.4,
          transition: "stroke-width 0.8s, stroke 0.8s, opacity 0.8s",
        }}
      />
      
      {/* Neural Gradient Flow (Visible for Active Edges) */}
      <AnimatePresence>
        {isActive && (
          <motion.path
            d={edgePath}
            fill="none"
            strokeWidth={4}
            stroke={color}
            strokeLinecap="round"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: [0, 0.4, 0] }}
            exit={{ opacity: 0 }}
            transition={{
              duration: 2.5,
              repeat: Infinity,
              ease: "linear",
            }}
            className="pointer-events-none blur-[4px]"
          />
        )}
      </AnimatePresence>

      {/* Pulsing Particle Flow Effect */}
      <AnimatePresence>
        {isActive && (
          <>
            <motion.path
              d={edgePath}
              fill="none"
              strokeWidth={1.5}
              stroke="white"
              strokeDasharray="1, 15"
              strokeLinecap="round"
              initial={{ strokeDashoffset: 24 }}
              animate={{ strokeDashoffset: 0 }}
              transition={{
                duration: 1.2,
                repeat: Infinity,
                ease: "linear",
              }}
              style={{ filter: `drop-shadow(0 0 5px ${color})` }}
              className="pointer-events-none"
            />
            
            {/* Travelling Data Particle - WOW Factor */}
            <motion.circle
               r="3"
               fill={color}
               initial={{ opacity: 0, scale: 0.5 }}
               animate={{ 
                 offsetDistance: ["0%", "100%"], 
                 opacity: [0, 1, 0],
                 scale: [0.5, 1.2, 0.5]
               }}
               transition={{
                 duration: 2,
                 repeat: Infinity,
                 ease: "linear"
               }}
               style={{ 
                 motionPath: `path("${edgePath}")`,
                 filter: `blur(0.5px) drop-shadow(0 0 8px ${color})`
               }}
               className="pointer-events-none"
            />
          </>
        )}
      </AnimatePresence>
    </>
  );
});

AnimatedEdge.displayName = "AnimatedEdge";
