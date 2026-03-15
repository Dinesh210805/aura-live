import React from 'react';
import {Img, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

type PhoneMockupProps = {
  src: string;
  width?: number;
  delay?: number;
  cinematicTilt?: boolean;
};

export const PhoneMockup: React.FC<PhoneMockupProps> = ({src, width = 440, delay = 0, cinematicTilt = true}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({
    frame: frame - delay,
    fps,
    config: {stiffness: 300, damping: 20},
  });
  const rotateY = cinematicTilt ? interpolate(enter, [0, 1], [8, 0]) : 0;
  const translateX = interpolate(enter, [0, 1], [180, 0]);

  const height = width * 2.12;
  const border = 18;

  return (
    <div
      style={{
        width,
        height,
        borderRadius: 56,
        background: 'linear-gradient(160deg, #1D2538 0%, #090B11 100%)',
        border: `${border}px solid #0F111A`,
        boxShadow: '0 30px 90px rgba(0,0,0,0.6)',
        overflow: 'hidden',
        transform: `translateX(${translateX}px) rotateY(${rotateY}deg)`,
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: '50%',
          transform: 'translateX(-50%)',
          top: 10,
          width: 130,
          height: 18,
          borderRadius: 12,
          background: '#0A0A0A',
          zIndex: 4,
        }}
      />
      <div
        style={{
          position: 'absolute',
          top: border,
          left: border,
          right: border,
          bottom: border,
          borderRadius: 40,
          overflow: 'hidden',
          background: '#000',
        }}
      >
        <Img src={src} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </div>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: 56,
          boxShadow: 'inset 0 2px 8px rgba(255,255,255,0.12), inset 0 -8px 20px rgba(0,0,0,0.45)',
          pointerEvents: 'none',
        }}
      />
    </div>
  );
};
