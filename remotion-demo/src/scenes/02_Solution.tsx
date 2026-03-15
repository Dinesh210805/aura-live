import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {VideoProps} from '../Video';
import {GradientMesh} from '../components/GradientMesh';
import {ParticleField} from '../components/ParticleField';
import {PhoneMockup} from '../components/PhoneMockup';
import {Spotlight} from '../components/Spotlight';
import {Glitch} from '../components/transitions/Glitch';

type SolutionSceneProps = VideoProps & {
  durationInFrames: number;
};

export const SolutionScene: React.FC<SolutionSceneProps> = ({projectName, tagline, heroFeature, palette, durationInFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const flash = interpolate(frame, [0, 12], [0.85, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.in(Easing.quad),
  });
  const titleIn = spring({frame: frame - 20, fps, config: {stiffness: 300, damping: 20}});
  const contentOpacity = interpolate(frame, [24, 90], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <AbsoluteFill>
      <GradientMesh
        accent1={palette.accent1}
        accent2={palette.accent2}
        accent3={palette.accent3}
        bg={palette.bgDeep}
      />
      <AbsoluteFill style={{opacity: interpolate(frame, [0, 120], [0.45, 0.28])}}>
        <ParticleField particleCount={300} opacity={0.6} />
      </AbsoluteFill>
      <Spotlight durationInFrames={durationInFrames} radius={360} intensity={0.09} />

      <div style={{position: 'absolute', left: 110, top: 170, width: 900, opacity: contentOpacity}}>
        <div
          style={{
            fontSize: 96,
            fontWeight: 900,
            color: palette.textPrimary,
            letterSpacing: '0.09em',
            transform: `translateY(${interpolate(titleIn, [0, 1], [26, 0])}px)`,
            textShadow: '0 0 50px rgba(0,229,255,0.24)',
          }}
        >
          {projectName}
        </div>
        <div style={{marginTop: 18, fontSize: 40, color: palette.textPrimary}}>{tagline}</div>
        <div style={{marginTop: 34, fontSize: 30, color: palette.textMuted, maxWidth: 880}}>{heroFeature}</div>
      </div>

      <div style={{position: 'absolute', right: 180, top: 84}}>
        <PhoneMockup src={staticFile('screens/current_screen.png')} width={430} delay={45} cinematicTilt />
      </div>

      <div
        style={{
          position: 'absolute',
          left: 110,
          bottom: 150,
          fontSize: 26,
          color: 'rgba(255,255,255,0.72)',
          padding: '16px 22px',
          border: '1px solid rgba(255,255,255,0.15)',
          borderRadius: 14,
          background: 'rgba(255,255,255,0.03)',
        }}
      >
        Gemini 2.5 Flash primary VLM + Groq fallback routing
      </div>

      <AbsoluteFill style={{backgroundColor: '#FFF', opacity: flash}} />
      {frame <= 12 ? <Glitch durationInFrames={12} /> : null}
    </AbsoluteFill>
  );
};
