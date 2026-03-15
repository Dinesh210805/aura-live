import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {VideoProps} from '../Video';
import {AudioReactive} from '../components/AudioReactive';
import {CodeWindow} from '../components/CodeWindow';
import {PhoneMockup} from '../components/PhoneMockup';
import {Spotlight} from '../components/Spotlight';

type DemoSceneProps = VideoProps & {
  durationInFrames: number;
};

const screenshotTimeline = [
  staticFile('screens/current_screen.png'),
  staticFile('screens/voice_settings_test.png'),
  staticFile('screens/debug_screenshot.png'),
] as const;

const codeLines = [
  'package com.aura.aura_ui.data.repository',
  '',
  'class AssistantRepositoryImpl @Inject constructor(',
  '    private val auraApiService: AuraApiService,',
  '    private val logger: Logger,',
  ') : AssistantRepository {',
  '    override suspend fun processTextCommand(text: String) {',
  '        _voiceSessionState.value = VoiceSessionState.Processing(',
  '            "Sending command to AURA backend"',
  '        )',
  '        val request = TaskRequestDto(',
  '            audioData = text,',
  '            inputType = "text"',
  '        )',
  '        val response = auraApiService.executeTask(request)',
  '        if (response.isSuccessful && response.body() != null) {',
  '            _voiceSessionState.value = VoiceSessionState.Responding(',
  '                response.body()!!.spokenResponse',
  '            )',
  '        }',
  '    }',
  '}',
] as const;

const labelData = [
  {text: 'Live overlay', x: 360, y: 320, start: 90},
  {text: 'Voice status', x: 430, y: 560, start: 180},
  {text: 'Command reply', x: 430, y: 700, start: 280},
] as const;

export const DemoScene: React.FC<DemoSceneProps> = ({durationInFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const shotSpan = Math.floor(durationInFrames / screenshotTimeline.length);
  const shotIndex = Math.min(screenshotTimeline.length - 1, Math.floor(frame / shotSpan));
  const shotStart = shotIndex * shotSpan;
  const shotProgress = interpolate(frame - shotStart, [0, 40], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <AbsoluteFill style={{backgroundColor: '#050814'}}>
      <AudioReactive opacity={0.2} />
      <Spotlight durationInFrames={durationInFrames} radius={270} intensity={0.08} />

      <div
        style={{
          position: 'absolute',
          left: 120,
          top: 90,
          fontSize: 62,
          fontWeight: 900,
          color: '#FFFFFF',
        }}
      >
        Live Android walkthrough
      </div>

      <div
        style={{
          position: 'absolute',
          left: 130,
          top: 220,
          transform: `translateX(${interpolate(shotProgress, [0, 1], [50, 0])}px)`,
          opacity: shotProgress,
        }}
      >
        <PhoneMockup src={screenshotTimeline[shotIndex]} width={430} cinematicTilt={false} />
      </div>

      {labelData.map((label) => {
        const pop = spring({frame: frame - label.start, fps, config: {stiffness: 320, damping: 19}});
        return (
          <div
            key={label.text}
            style={{
              position: 'absolute',
              left: label.x,
              top: label.y,
              transform: `scale(${0.6 + 0.4 * pop})`,
              opacity: pop,
              background: 'rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.24)',
              borderRadius: 12,
              padding: '8px 12px',
              color: '#FFFFFF',
              fontSize: 20,
              backdropFilter: 'blur(10px)',
            }}
          >
            {label.text}
          </div>
        );
      })}

      <div style={{position: 'absolute', right: 90, top: 180}}>
        <CodeWindow title="AssistantRepositoryImpl.kt" lines={[...codeLines]} width={930} height={580} delay={80} />
      </div>
    </AbsoluteFill>
  );
};
