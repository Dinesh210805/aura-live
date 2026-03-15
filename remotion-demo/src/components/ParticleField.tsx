import React, {useEffect, useMemo, useRef} from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';

type ParticleFieldProps = {
  particleCount?: number;
  opacity?: number;
};

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
};

const WIDTH = 1920;
const HEIGHT = 1080;
const LINK_DISTANCE = 120;

export const ParticleField: React.FC<ParticleFieldProps> = ({particleCount = 320, opacity = 1}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const particles = useMemo<Particle[]>(() => {
    return Array.from({length: particleCount}).map((_, index) => {
      const seed = Math.sin(index * 12.9898) * 43758.5453;
      const fractional = seed - Math.floor(seed);
      return {
        x: (index * 37.7) % WIDTH,
        y: (index * 71.3) % HEIGHT,
        vx: -0.35 + fractional * 0.7,
        vy: -0.35 + (1 - fractional) * 0.7,
        size: 1 + (index % 3),
        alpha: 0.2 + (index % 5) * 0.1,
      };
    });
  }, [particleCount]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    const context = canvas.getContext('2d');
    if (!context) {
      return;
    }

    context.clearRect(0, 0, WIDTH, HEIGHT);
    const elapsed = frame / fps;

    const dynamicParticles = particles.map((particle, index) => {
      const x = (particle.x + particle.vx * frame * 0.9 + Math.sin(elapsed + index) * 0.6 + WIDTH) % WIDTH;
      const y = (particle.y + particle.vy * frame * 0.9 + Math.cos(elapsed * 0.8 + index) * 0.6 + HEIGHT) % HEIGHT;
      return {...particle, x, y};
    });

    for (let i = 0; i < dynamicParticles.length; i++) {
      const current = dynamicParticles[i];
      context.beginPath();
      context.fillStyle = `rgba(180,240,255,${current.alpha * opacity})`;
      context.arc(current.x, current.y, current.size, 0, Math.PI * 2);
      context.fill();

      for (let j = i + 1; j < dynamicParticles.length; j++) {
        const target = dynamicParticles[j];
        const dx = current.x - target.x;
        const dy = current.y - target.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < LINK_DISTANCE) {
          const linkAlpha = ((LINK_DISTANCE - distance) / LINK_DISTANCE) * 0.12 * opacity;
          context.beginPath();
          context.strokeStyle = `rgba(0,229,255,${linkAlpha})`;
          context.lineWidth = 1;
          context.moveTo(current.x, current.y);
          context.lineTo(target.x, target.y);
          context.stroke();
        }
      }
    }
  }, [frame, fps, particles, opacity]);

  return <canvas ref={canvasRef} width={WIDTH} height={HEIGHT} style={{width: '100%', height: '100%'}} />;
};
