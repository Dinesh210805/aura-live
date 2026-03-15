import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {VideoProps} from '../Video';
import {ZoomBlur} from '../components/transitions/ZoomBlur';

type ProblemSceneProps = VideoProps & {
  durationInFrames: number;
};

const painBullets = [
  '✗ brittle one-shot vision guesses fail in real apps',
  '✗ static plans collapse when screens shift mid-task',
  '✗ unsafe actions need policy and human guardrails',
] as const;

export const ProblemScene: React.FC<ProblemSceneProps> = ({palette}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const titleIn = spring({frame: frame - 24, fps, config: {stiffness: 300, damping: 20}});
  const mockupShake = Math.sin(frame * 0.8) * (frame < 260 ? 5 : 1);

  return (
    <AbsoluteFill style={{backgroundColor: '#0A0C14'}}>
      <ZoomBlur frame={frame} durationInFrames={24}>
        <AbsoluteFill
          style={{
            justifyContent: 'center',
            alignItems: 'center',
            background:
              'radial-gradient(circle at 30% 30%, rgba(255,107,107,0.20), transparent 40%), radial-gradient(circle at 70% 70%, rgba(123,97,255,0.16), transparent 44%), #0A0C14',
          }}
        />
      </ZoomBlur>

      <div
        style={{
          position: 'absolute',
          top: 140,
          left: 120,
          right: 120,
          fontSize: 72,
          fontWeight: 900,
          textAlign: 'center',
          color: 'rgba(255,255,255,0.9)',
          transform: `translateY(${interpolate(titleIn, [0, 1], [24, 0])}px)`,
          opacity: titleIn,
        }}
      >
        Voice automation breaks when the UI fights back.
      </div>

      <div
        style={{
          position: 'absolute',
          left: 270,
          right: 270,
          top: 330,
          height: 430,
          borderRadius: 24,
          border: `1px solid rgba(255,107,107,0.22)`,
          background: 'rgba(255,255,255,0.03)',
          filter: `grayscale(0.75) contrast(0.9) hue-rotate(-15deg)`,
          transform: `translateX(${mockupShake}px)`,
        }}
      />

      <div style={{position: 'absolute', left: 220, right: 220, bottom: 120, display: 'grid', gap: 20}}>
        {painBullets.map((bullet, index) => {
          const start = 80 + index * 80;
          const progress = spring({frame: frame - start, fps, config: {stiffness: 280, damping: 20}});
          return (
            <div
              key={bullet}
              style={{
                fontSize: 38,
                color: index === 2 ? palette.accent3 : 'rgba(255,255,255,0.76)',
                opacity: progress,
                transform: `translateY(${interpolate(progress, [0, 1], [24, 0])}px)`,
              }}
            >
              {bullet}
            </div>
          );
        })}
      </div>

      <AbsoluteFill
        style={{
          backgroundColor: '#050507',
          opacity: interpolate(frame, [560, 600], [0, 0.65], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.in(Easing.quad),
          }),
        }}
      />
    </AbsoluteFill>
  );
};
