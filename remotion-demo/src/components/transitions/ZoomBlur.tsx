import React from 'react';
import {interpolate, Easing} from 'remotion';

type ZoomBlurProps = {
  frame: number;
  durationInFrames: number;
  children: React.ReactNode;
};

export const ZoomBlur: React.FC<ZoomBlurProps> = ({frame, durationInFrames, children}) => {
  const progress = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const scale = interpolate(progress, [0, 1], [1, 0.95]);
  const blur = interpolate(progress, [0, 1], [0, 8]);

  return (
    <div style={{position: 'absolute', inset: 0, transform: `scale(${scale})`, filter: `blur(${blur}px)`}}>
      {children}
    </div>
  );
};
