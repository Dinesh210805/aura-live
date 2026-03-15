import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {z} from 'zod';
import {IntroScene} from './scenes/00_Intro';
import {ProblemScene} from './scenes/01_Problem';
import {SolutionScene} from './scenes/02_Solution';
import {FeaturesScene} from './scenes/03_Features';
import {DemoScene} from './scenes/04_Demo';
import {ArchitectureScene} from './scenes/05_Architecture';
import {CTAScene} from './scenes/06_CTA';

const featureSchema = z.object({
  title: z.string(),
  description: z.string(),
  badge: z.string(),
});

const paletteSchema = z.object({
  bgDeep: z.string(),
  bgCard: z.string(),
  accent1: z.string(),
  accent2: z.string(),
  accent3: z.string(),
  textPrimary: z.string(),
  textMuted: z.string(),
});

const metricsSchema = z.object({
  kotlinFiles: z.number(),
  kotlinLines: z.number(),
  screenFiles: z.number(),
  maxActions: z.number(),
});

export const videoPropsSchema = z.object({
  projectName: z.string(),
  tagline: z.string(),
  heroFeature: z.string(),
  accentColor: z.string(),
  features: z.array(featureSchema).length(3),
  techStackBadges: z.array(z.string()),
  palette: paletteSchema,
  metrics: metricsSchema,
});

export type VideoProps = z.infer<typeof videoPropsSchema>;

export const SCENE_FRAMES = {
  intro: 480,
  problem: 600,
  solution: 720,
  features: 1320,
  demo: 1080,
  architecture: 600,
  cta: 600,
} as const;

export const Video: React.FC<VideoProps> = (props) => {
  const starts = {
    intro: 0,
    problem: SCENE_FRAMES.intro,
    solution: SCENE_FRAMES.intro + SCENE_FRAMES.problem,
    features: SCENE_FRAMES.intro + SCENE_FRAMES.problem + SCENE_FRAMES.solution,
    demo:
      SCENE_FRAMES.intro +
      SCENE_FRAMES.problem +
      SCENE_FRAMES.solution +
      SCENE_FRAMES.features,
    architecture:
      SCENE_FRAMES.intro +
      SCENE_FRAMES.problem +
      SCENE_FRAMES.solution +
      SCENE_FRAMES.features +
      SCENE_FRAMES.demo,
    cta:
      SCENE_FRAMES.intro +
      SCENE_FRAMES.problem +
      SCENE_FRAMES.solution +
      SCENE_FRAMES.features +
      SCENE_FRAMES.demo +
      SCENE_FRAMES.architecture,
  } as const;

  return (
    <AbsoluteFill style={{backgroundColor: props.palette.bgDeep, fontFamily: 'Inter, sans-serif'}}>
      <Audio src={staticFile('sfx/ambient.wav')} volume={0.12} />
      <Sequence from={starts.solution} durationInFrames={24}>
        <Audio src={staticFile('sfx/impact.wav')} volume={0.45} />
      </Sequence>
      <Sequence from={starts.features} durationInFrames={24}>
        <Audio src={staticFile('sfx/whoosh.wav')} volume={0.3} />
      </Sequence>
      <Sequence from={starts.demo + 120} durationInFrames={80}>
        <Audio src={staticFile('sfx/type.wav')} volume={0.15} />
      </Sequence>

      <Sequence from={starts.intro} durationInFrames={SCENE_FRAMES.intro}>
        <IntroScene {...props} durationInFrames={SCENE_FRAMES.intro} />
      </Sequence>

      <Sequence from={starts.problem} durationInFrames={SCENE_FRAMES.problem}>
        <ProblemScene {...props} durationInFrames={SCENE_FRAMES.problem} />
      </Sequence>

      <Sequence from={starts.solution} durationInFrames={SCENE_FRAMES.solution}>
        <SolutionScene {...props} durationInFrames={SCENE_FRAMES.solution} />
      </Sequence>

      <Sequence from={starts.features} durationInFrames={SCENE_FRAMES.features}>
        <FeaturesScene {...props} durationInFrames={SCENE_FRAMES.features} />
      </Sequence>

      <Sequence from={starts.demo} durationInFrames={SCENE_FRAMES.demo}>
        <DemoScene {...props} durationInFrames={SCENE_FRAMES.demo} />
      </Sequence>

      <Sequence from={starts.architecture} durationInFrames={SCENE_FRAMES.architecture}>
        <ArchitectureScene {...props} durationInFrames={SCENE_FRAMES.architecture} />
      </Sequence>

      <Sequence from={starts.cta} durationInFrames={SCENE_FRAMES.cta}>
        <CTAScene {...props} durationInFrames={SCENE_FRAMES.cta} />
      </Sequence>
    </AbsoluteFill>
  );
};
