import React from "react";
import { Composition } from "remotion";
import { ArchDiagram } from "./ArchDiagram";

// 30 seconds at 30fps = 900 frames
const DURATION_FRAMES = 900;
const FPS = 30;

export const Root: React.FC = () => {
  return (
    <Composition
      id="ArchDiagram"
      component={ArchDiagram}
      durationInFrames={DURATION_FRAMES}
      fps={FPS}
      width={1920}
      height={1080}
    />
  );
};
