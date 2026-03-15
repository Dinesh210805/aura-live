import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';

type GradientMeshProps = {
  accent1: string;
  accent2: string;
  accent3: string;
  bg: string;
};

export const GradientMesh: React.FC<GradientMeshProps> = ({accent1, accent2, accent3, bg}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const x1 = 50 + 20 * Math.sin(t * 0.3);
  const y1 = 50 + 15 * Math.cos(t * 0.2);
  const x2 = 40 + 24 * Math.cos(t * 0.27);
  const y2 = 42 + 18 * Math.sin(t * 0.24);

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        background: [
          `radial-gradient(circle at ${x1}% ${y1}%, ${accent1}44 0%, transparent 48%)`,
          `radial-gradient(circle at ${x2}% ${y2}%, ${accent2}3A 0%, transparent 50%)`,
          `radial-gradient(circle at 72% 65%, ${accent3}24 0%, transparent 52%)`,
          bg,
        ].join(','),
      }}
    />
  );
};
