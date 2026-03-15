import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {VideoProps} from '../Video';
import {CountUp} from '../components/CountUp';

type ArchitectureSceneProps = VideoProps & {
  durationInFrames: number;
};

const layerBoxes = [
  {title: 'UI Layer', subtitle: 'MainActivity + VoiceConversationActivity', x: 120, y: 210},
  {title: 'ViewModel', subtitle: 'AssistantViewModel', x: 560, y: 210},
  {title: 'Repository', subtitle: 'AssistantRepositoryImpl', x: 1000, y: 210},
  {title: 'Data Sources', subtitle: 'AuraApiService + AuraDatabase', x: 1440, y: 210},
] as const;

export const ArchitectureScene: React.FC<ArchitectureSceneProps> = ({techStackBadges, metrics}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <AbsoluteFill
      style={{
        background:
          'radial-gradient(circle at 20% 80%, rgba(0,229,255,0.12), transparent 46%), radial-gradient(circle at 80% 30%, rgba(123,97,255,0.18), transparent 44%), #050814',
      }}
    >
      <div style={{position: 'absolute', top: 70, width: '100%', textAlign: 'center', color: '#FFFFFF', fontSize: 60, fontWeight: 900}}>
        Production architecture credibility
      </div>

      <svg width={1920} height={1080} style={{position: 'absolute', inset: 0}}>
        {Array.from({length: layerBoxes.length - 1}).map((_, index) => {
          const startX = layerBoxes[index].x + 330;
          const endX = layerBoxes[index + 1].x;
          const y = 305;
          const local = spring({frame: frame - 60 - index * 16, fps, config: {stiffness: 220, damping: 18}});
          const lineProgress = interpolate(local, [0, 1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
          return (
            <line
              key={`connector-${index}`}
              x1={startX}
              y1={y}
              x2={startX + (endX - startX) * lineProgress}
              y2={y}
              stroke="rgba(0,229,255,0.8)"
              strokeWidth={4}
              strokeLinecap="round"
            />
          );
        })}
      </svg>

      {layerBoxes.map((layer, index) => {
        const reveal = spring({frame: frame - 40 - index * 12, fps, config: {stiffness: 250, damping: 18}});
        return (
          <div
            key={layer.title}
            style={{
              position: 'absolute',
              left: layer.x,
              top: layer.y,
              width: 330,
              height: 190,
              borderRadius: 18,
              background: 'rgba(13,21,37,0.78)',
              border: '1px solid rgba(255,255,255,0.2)',
              boxShadow: '0 0 35px rgba(0,229,255,0.16)',
              opacity: reveal,
              transform: `translateY(${interpolate(reveal, [0, 1], [24, 0])}px)`,
              padding: 18,
            }}
          >
            <div style={{fontSize: 34, color: '#FFFFFF', fontWeight: 800}}>{layer.title}</div>
            <div style={{marginTop: 14, fontSize: 20, color: 'rgba(255,255,255,0.72)', lineHeight: 1.3}}>{layer.subtitle}</div>
          </div>
        );
      })}

      <div style={{position: 'absolute', left: 120, right: 120, bottom: 240, display: 'flex', flexWrap: 'wrap', gap: 14}}>
        {techStackBadges.map((badge, index) => {
          const appear = spring({frame: frame - 200 - index * 6, fps, config: {stiffness: 320, damping: 18}});
          return (
            <div
              key={badge}
              style={{
                padding: '10px 14px',
                borderRadius: 999,
                border: '1px solid rgba(255,255,255,0.22)',
                background: 'rgba(255,255,255,0.05)',
                color: '#FFFFFF',
                fontSize: 22,
                transform: `scale(${0.72 + 0.28 * appear})`,
                opacity: appear,
              }}
            >
              {badge}
            </div>
          );
        })}
      </div>

      <div style={{position: 'absolute', left: 120, bottom: 90, color: '#FFFFFF'}}>
        <div style={{fontSize: 22, opacity: 0.7, marginBottom: 4}}>Kotlin codebase depth</div>
        <CountUp target={metrics.kotlinLines} suffix="+" durationFrames={140} fontSize={82} color="#00E5FF" />
      </div>
    </AbsoluteFill>
  );
};
