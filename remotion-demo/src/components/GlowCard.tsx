import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';

type GlowCardProps = {
  children: React.ReactNode;
  delay?: number;
  width?: number;
  height?: number;
};

export const GlowCard: React.FC<GlowCardProps> = ({children, delay = 0, width = 560, height = 320}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = spring({
    frame: frame - delay,
    fps,
    config: {stiffness: 200, damping: 22},
  });

  const y = 40 - 40 * progress;
  const scale = 0.96 + 0.04 * progress;
  const opacity = progress;

  return (
    <div
      style={{
        width,
        height,
        borderRadius: 24,
        border: `1px solid rgba(0,229,255,${0.15 + 0.25 * progress})`,
        boxShadow: `0 0 ${20 + 20 * progress}px rgba(0,229,255,0.2)`,
        backdropFilter: 'blur(12px)',
        background: 'rgba(13,21,37,0.7)',
        transform: `translateY(${y}px) scale(${scale})`,
        opacity,
        padding: 28,
      }}
    >
      {children}
    </div>
  );
};
