import React from 'react';
import {interpolate, Easing} from 'remotion';

type SlideWipeProps = {
  frame: number;
  durationInFrames: number;
  color: string;
};

export const SlideWipe: React.FC<SlideWipeProps> = ({frame, durationInFrames, color}) => {
  const progress = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        transform: `translateX(${interpolate(progress, [0, 1], [-110, 110])}%)`,
        background: `linear-gradient(90deg, transparent 0%, ${color} 50%, transparent 100%)`,
        opacity: 0.8,
        pointerEvents: 'none',
      }}
    />
  );
};
