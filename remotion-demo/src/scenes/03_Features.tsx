import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {VideoProps} from '../Video';
import {GlowCard} from '../components/GlowCard';

type FeaturesSceneProps = VideoProps & {
  durationInFrames: number;
};

const FEATURE_BEAT = 440;
const FEATURE_OVERLAP = 90;

const snippetMap = [
  [
    'AURA perception bundle:',
    'ui_tree + screenshot + vlm_description',
    'webview -> force VLM fast-path',
  ],
  [
    'Coordinator constants:',
    'MAX_TOTAL_ACTIONS = 30',
    'MAX_REPLAN_ATTEMPTS = 3',
  ],
  [
    'Policy path:',
    'every gesture -> OPA policy check',
    'blocked actions -> safe speak response',
  ],
] as const;

export const FeaturesScene: React.FC<FeaturesSceneProps> = ({features, palette}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <AbsoluteFill
      style={{
        background:
          'radial-gradient(circle at 25% 20%, rgba(0,229,255,0.12), transparent 40%), radial-gradient(circle at 80% 60%, rgba(123,97,255,0.16), transparent 44%), #050814',
      }}
    >
      <div style={{position: 'absolute', top: 76, width: '100%', textAlign: 'center', color: '#FFFFFF', fontSize: 64, fontWeight: 900}}>
        Why AURA stands out
      </div>

      {features.map((feature, index) => {
        const start = index * FEATURE_BEAT - (index === 0 ? 0 : FEATURE_OVERLAP);
        const localFrame = frame - start;
        const enter = spring({frame: localFrame, fps, config: {stiffness: 300, damping: 20}});
        const out = interpolate(localFrame, [FEATURE_BEAT - 70, FEATURE_BEAT], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.in(Easing.quad),
        });
        const cardOpacity = enter * (1 - out);
        const blur = interpolate(out, [0, 1], [0, 8]);
        const scale = interpolate(out, [0, 1], [1, 0.92]);

        const baseTop = 180 + (index % 2) * 170;
        const baseLeft = 130 + index * 540;

        return (
          <div
            key={feature.title}
            style={{
              position: 'absolute',
              left: baseLeft,
              top: baseTop,
              opacity: cardOpacity,
              filter: `blur(${blur}px)`,
              transform: `scale(${scale})`,
            }}
          >
            <GlowCard width={500} height={340} delay={0}>
              <div style={{fontSize: 48, color: '#FFFFFF', fontWeight: 900, lineHeight: 1.05}}>{feature.title}</div>
              <div style={{marginTop: 16, fontSize: 22, color: 'rgba(255,255,255,0.72)', lineHeight: 1.35}}>
                {feature.description}
              </div>

              <div
                style={{
                  marginTop: 18,
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 17,
                  color: '#A7FFF8',
                  background: 'rgba(0,0,0,0.25)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 10,
                  padding: '12px 14px',
                  lineHeight: 1.4,
                }}
              >
                {snippetMap[index].map((line) => (
                  <div key={line}>{line}</div>
                ))}
              </div>

              <div
                style={{
                  marginTop: 18,
                  display: 'inline-flex',
                  padding: '8px 14px',
                  borderRadius: 999,
                  fontSize: 18,
                  color: palette.bgDeep,
                  background: 'linear-gradient(90deg, #00E5FF, #7B61FF)',
                  transform: `scale(${0.86 + 0.14 * enter})`,
                  transformOrigin: 'left center',
                }}
              >
                {feature.badge}
              </div>
            </GlowCard>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
