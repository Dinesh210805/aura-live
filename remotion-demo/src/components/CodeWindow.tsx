import React from 'react';
import {interpolate, Easing, useCurrentFrame} from 'remotion';

type CodeWindowProps = {
  title: string;
  lines: string[];
  width?: number;
  height?: number;
  delay?: number;
};

const keywordSet = new Set([
  'package',
  'import',
  'class',
  'interface',
  'override',
  'suspend',
  'fun',
  'val',
  'var',
  'return',
  'if',
  'else',
  'try',
  'catch',
]);

const tokenize = (line: string): {text: string; color: string}[] => {
  if (line.trim().startsWith('//')) {
    return [{text: line, color: '#808080'}];
  }

  const parts = line.split(/("[^"]*"|\s+|\(|\)|\{|\}|\.|,|:|=)/).filter((p) => p !== '');
  return parts.map((part) => {
    if (part.startsWith('"') && part.endsWith('"')) {
      return {text: part, color: '#6A8759'};
    }
    if (keywordSet.has(part.trim())) {
      return {text: part, color: '#CC7832'};
    }
    return {text: part, color: '#E6EDF3'};
  });
};

export const CodeWindow: React.FC<CodeWindowProps> = ({title, lines, width = 900, height = 430, delay = 0}) => {
  const frame = useCurrentFrame();
  const eased = interpolate(frame - delay, [0, 45], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const allChars = lines.join('\n');
  const typedCharCount = Math.floor(Math.max(0, frame - delay) / 2);
  const visibleCharCount = Math.min(allChars.length, typedCharCount);

  let consumed = 0;

  return (
    <div
      style={{
        width,
        height,
        background: 'rgba(9,14,25,0.92)',
        border: '1px solid rgba(255,255,255,0.12)',
        borderRadius: 18,
        boxShadow: '0 20px 60px rgba(0,0,0,0.45)',
        transform: `scale(${0.92 + 0.08 * eased})`,
        opacity: eased,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          height: 44,
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 14px',
          color: 'rgba(255,255,255,0.78)',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 16,
        }}
      >
        {title}
      </div>
      <div
        style={{
          padding: '14px 18px',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 20,
          lineHeight: 1.45,
        }}
      >
        {lines.map((line, lineIndex) => {
          const lineLength = line.length + 1;
          const canRenderCount = Math.max(0, Math.min(line.length, visibleCharCount - consumed));
          consumed += lineLength;
          const visibleText = line.slice(0, canRenderCount);
          const tokens = tokenize(visibleText);

          return (
            <div key={`line-${lineIndex}`} style={{display: 'flex', flexWrap: 'wrap'}}>
              {tokens.map((token, tokenIndex) => (
                <span key={`token-${lineIndex}-${tokenIndex}`} style={{color: token.color, whiteSpace: 'pre'}}>
                  {token.text}
                </span>
              ))}
            </div>
          );
        })}
        <span
          style={{
            display: 'inline-block',
            width: 10,
            height: 24,
            marginTop: 4,
            backgroundColor: frame % 120 < 60 ? 'rgba(255,255,255,0.86)' : 'transparent',
          }}
        />
      </div>
    </div>
  );
};
