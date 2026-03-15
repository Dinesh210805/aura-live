import React from 'react';
import {Composition} from 'remotion';
import {z} from 'zod';
import {Video, videoPropsSchema} from './Video';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="DemoVideo"
        component={Video}
        durationInFrames={5400}
        fps={60}
        width={1920}
        height={1080}
        schema={videoPropsSchema}
        defaultProps={{
          projectName: 'AURA',
          tagline: 'Voice that turns intent into Android action.',
          heroFeature: '3-layer perception plus 9-agent execution loop.',
          accentColor: '#FFFFFF',
          features: [
            {
              title: 'Hybrid Perception',
              description:
                'Combines UI tree, YOLOv8 detection, and VLM element selection.',
              badge: '3-Layer',
            },
            {
              title: 'Goal-Driven Coordination',
              description:
                'Runs perceive-decide-act-verify with retries before replanning.',
              badge: '9 Agents',
            },
            {
              title: 'Real Device Control',
              description:
                'Executes gestures through Android Accessibility with policy checks.',
              badge: 'Live Android',
            },
          ],
          techStackBadges: [
            'Kotlin',
            'Jetpack Compose',
            'Coroutines',
            'Retrofit',
            'Hilt',
            'FastAPI',
            'LangGraph',
            'Gemini 2.5 Flash',
          ],
          palette: {
            bgDeep: '#050814',
            bgCard: '#0D1525',
            accent1: '#00E5FF',
            accent2: '#7B61FF',
            accent3: '#FF6B6B',
            textPrimary: '#FFFFFF',
            textMuted: 'rgba(255,255,255,0.65)',
          },
          metrics: {
            kotlinFiles: 113,
            kotlinLines: 31461,
            screenFiles: 8,
            maxActions: 30,
          },
        }}
      />
    </>
  );
};

export type RemotionRootProps = z.infer<typeof videoPropsSchema>;
