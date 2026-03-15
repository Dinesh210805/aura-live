import React from 'react';
import {interpolate, Easing, useCurrentFrame, useVideoConfig} from 'remotion';

type CountUpProps = {
  target: number;
  suffix?: string;
  prefix?: string;
  delay?: number;
  durationFrames?: number;
  fontSize?: number;
  color?: string;
};

export const CountUp: React.FC<CountUpProps> = ({
  target,
  suffix = '',
  prefix = '',
  delay = 0,
  durationFrames = 120,
  fontSize = 72,
  color = '#FFFFFF',
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const progress = interpolate(frame - delay, [0, durationFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const value = Math.round(target * progress);
  const formatter = new Intl.NumberFormat('en-US');

  return (
    <span style={{fontSize, color, fontWeight: 900, lineHeight: 1.05}}>
      {prefix}
      {formatter.format(value)}
      {suffix}
      <span style={{opacity: 0.6, marginLeft: 8, fontSize: fontSize * 0.42}}>{fps}fps</span>
    </span>
  );
};
