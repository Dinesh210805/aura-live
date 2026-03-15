import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {VideoProps} from '../Video';
import {AnimatedText} from '../components/AnimatedText';
import {GradientMesh} from '../components/GradientMesh';
import {ParticleField} from '../components/ParticleField';

type IntroSceneProps = VideoProps & {
  durationInFrames: number;
};

export const IntroScene: React.FC<IntroSceneProps> = ({projectName, tagline, palette, durationInFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const slam = spring({
    frame: frame - 20,
    fps,
    config: {stiffness: 280, damping: 18},
  });
  const scale = interpolate(slam, [0, 1], [0.78, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const taglineOpacity = spring({
    frame: frame - 30,
    fps,
    config: {stiffness: 120, damping: 16},
  });
  const chroma = interpolate(frame, [20, 55], [16, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const openingBlackOpacity = frame < 8 ? 1 : 0;
  const particleOpacity = interpolate(frame, [8, 90], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <GradientMesh
        accent1={palette.accent1}
        accent2={palette.accent2}
        accent3={palette.accent3}
        bg={palette.bgDeep}
      />
      <AbsoluteFill style={{opacity: particleOpacity}}>
        <ParticleField particleCount={520} opacity={0.95} />
      </AbsoluteFill>

      <div style={{position: 'relative', textAlign: 'center', transform: `scale(${scale})`}}>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            transform: `translateX(${chroma}px)`,
            color: 'rgba(0,229,255,0.28)',
            fontSize: 112,
            fontWeight: 900,
            letterSpacing: '0.12em',
          }}
        >
          {projectName}
        </div>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            transform: `translateX(${-chroma}px)`,
            color: 'rgba(255,90,130,0.22)',
            fontSize: 112,
            fontWeight: 900,
            letterSpacing: '0.12em',
          }}
        >
          {projectName}
        </div>
        <AnimatedText text={projectName} fontSize={112} letterSpacing="0.12em" staggerFrames={3} delay={20} />

        <div
          style={{
            marginTop: 26,
            fontSize: 40,
            opacity: taglineOpacity,
            color: palette.textMuted,
            letterSpacing: '0.02em',
          }}
        >
          {tagline}
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          bottom: 48,
          right: 60,
          color: 'rgba(255,255,255,0.42)',
          fontSize: 18,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}
      >
        0:00 / 1:30
      </div>

      <AbsoluteFill
        style={{
          backgroundColor: '#000',
          opacity: openingBlackOpacity + interpolate(frame, [durationInFrames - 24, durationInFrames], [0, 0.2], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.in(Easing.quad),
          }),
        }}
      />
    </AbsoluteFill>
  );
};
