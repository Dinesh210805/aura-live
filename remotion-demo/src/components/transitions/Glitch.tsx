import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';

type GlitchProps = {
  durationInFrames?: number;
};

const BAND_COUNT = 11;

export const Glitch: React.FC<GlitchProps> = ({durationInFrames = 12}) => {
  const frame = useCurrentFrame();
  const intensity = interpolate(frame, [0, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity: intensity}}>
      {Array.from({length: BAND_COUNT}).map((_, index) => {
        const seed = Math.sin((frame + 1) * (index + 3) * 77.123) * 10000;
        const random = seed - Math.floor(seed);
        const top = (index / BAND_COUNT) * 100;
        const height = 100 / BAND_COUNT;
        const offset = (random - 0.5) * 40;
        return (
          <div
            key={`band-${index}`}
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: `${top}%`,
              height: `${height}%`,
              transform: `translateX(${offset * intensity}px)`,
              background: 'linear-gradient(90deg, rgba(255,0,120,0.08), rgba(0,229,255,0.1))',
              mixBlendMode: 'screen',
            }}
          />
        );
      })}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          transform: `translateX(${3 * intensity}px)`,
          border: '2px solid rgba(0,229,255,0.2)',
          mixBlendMode: 'screen',
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          transform: `translateX(${-3 * intensity}px)`,
          border: '2px solid rgba(255,0,100,0.14)',
          mixBlendMode: 'screen',
        }}
      />
    </div>
  );
};
