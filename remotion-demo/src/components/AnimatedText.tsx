import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

type AnimatedTextProps = {
  text: string;
  color?: string;
  fontSize?: number;
  fontWeight?: number;
  letterSpacing?: string;
  staggerFrames?: number;
  delay?: number;
  align?: 'left' | 'center' | 'right';
};

export const AnimatedText: React.FC<AnimatedTextProps> = ({
  text,
  color = '#FFFFFF',
  fontSize = 64,
  fontWeight = 900,
  letterSpacing = '0.08em',
  staggerFrames = 3,
  delay = 0,
  align = 'center',
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const chars = [...text];

  return (
    <div style={{display: 'flex', justifyContent: align, flexWrap: 'wrap'}}>
      {chars.map((char, index) => {
        const charDelay = delay + index * staggerFrames;
        const progress = spring({
          frame: frame - charDelay,
          fps,
          config: {stiffness: 280, damping: 18},
        });
        const translateY = interpolate(progress, [0, 1], [30, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });

        return (
          <span
            key={`${char}-${index}`}
            style={{
              display: 'inline-block',
              transform: `translateY(${translateY}px)`,
              opacity: progress,
              color,
              fontSize,
              fontWeight,
              letterSpacing,
              whiteSpace: char === ' ' ? 'pre' : 'normal',
            }}
          >
            {char}
          </span>
        );
      })}
    </div>
  );
};
