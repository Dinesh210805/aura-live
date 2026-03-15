import React from 'react';
import {useCurrentFrame} from 'remotion';

type AudioReactiveProps = {
  bars?: number;
  opacity?: number;
};

export const AudioReactive: React.FC<AudioReactiveProps> = ({bars = 48, opacity = 0.2}) => {
  const frame = useCurrentFrame();
  const barWidth = 18;
  const gap = 10;

  return (
    <div
      style={{
        position: 'absolute',
        left: 80,
        right: 80,
        bottom: 30,
        height: 180,
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'center',
        gap,
        opacity,
      }}
    >
      {Array.from({length: bars}).map((_, index) => {
        const frequency = 0.04 + (index % 7) * 0.006;
        const phase = index * 0.35;
        const height = 20 + 80 * Math.abs(Math.sin(frame * frequency + phase));
        return (
          <div
            key={`bar-${index}`}
            style={{
              width: barWidth,
              height,
              borderRadius: 999,
              background: 'linear-gradient(180deg, #00E5FF 0%, #7B61FF 100%)',
            }}
          />
        );
      })}
    </div>
  );
};
