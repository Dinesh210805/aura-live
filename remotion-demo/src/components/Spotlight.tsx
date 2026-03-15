import React from 'react';
import {interpolate, Easing, useCurrentFrame} from 'remotion';

type SpotlightProps = {
  durationInFrames: number;
  radius?: number;
  intensity?: number;
};

export const Spotlight: React.FC<SpotlightProps> = ({durationInFrames, radius = 300, intensity = 0.07}) => {
  const frame = useCurrentFrame();
  const x = interpolate(frame, [0, durationInFrames], [240, 1680], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const y = interpolate(frame, [0, durationInFrames], [260, 860], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        background: `radial-gradient(circle ${radius}px at ${x}px ${y}px, rgba(255,255,255,${intensity}) 0%, transparent 70%)`,
      }}
    />
  );
};
