import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import {VideoProps} from '../Video';
import {ParticleField} from '../components/ParticleField';
import {SlideWipe} from '../components/transitions/SlideWipe';

type CTASceneProps = VideoProps & {
  durationInFrames: number;
};

export const CTAScene: React.FC<CTASceneProps> = ({projectName, tagline, palette, durationInFrames}) => {
  const frame = useCurrentFrame();
  const holdStart = durationInFrames - 120;
  const fadeOut = interpolate(frame, [holdStart - 60, holdStart], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.in(Easing.quad),
  });
  const finalLogoOpacity = interpolate(frame, [holdStart, holdStart + 30], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{
          background: `linear-gradient(135deg, ${palette.accent2} 0%, ${palette.accent1} 52%, ${palette.bgDeep} 100%)`,
          opacity: fadeOut,
        }}
      >
        <ParticleField particleCount={560} opacity={0.85} />
      </AbsoluteFill>

      <SlideWipe frame={frame} durationInFrames={34} color={palette.accent1} />

      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          opacity: fadeOut,
        }}
      >
        <div style={{fontSize: 148, fontWeight: 900, color: '#FFFFFF', letterSpacing: '0.1em'}}>{projectName}</div>
        <div style={{marginTop: 18, fontSize: 36, color: 'rgba(255,255,255,0.9)'}}>{tagline}</div>
        <div
          style={{
            marginTop: 54,
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 28,
            color: '#FFFFFF',
            borderRadius: 14,
            border: '1px solid rgba(255,255,255,0.34)',
            background: 'rgba(7,10,18,0.45)',
            padding: '18px 26px',
          }}
        >
          git clone github.com/Dinesh210805/aura-live
        </div>
      </div>

      <AbsoluteFill
        style={{
          backgroundColor: '#000',
          opacity: interpolate(frame, [holdStart - 30, holdStart], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.in(Easing.quad),
          }),
          justifyContent: 'center',
          alignItems: 'center',
        }}
      >
        <div style={{fontSize: 42, fontWeight: 800, color: '#FFFFFF', letterSpacing: '0.12em', opacity: finalLogoOpacity}}>
          {projectName}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
