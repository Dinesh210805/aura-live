import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate, spring } from "remotion";

// ── Canvas ────────────────────────────────────────────────────────────────────
const W = 1920;
const H = 1080;
const FPS = 30;
const NODE_W = 228;
const NODE_H = 62;

// ── Types ─────────────────────────────────────────────────────────────────────
interface NodeDef {
  id: string;
  label: string;
  sub?: string;
  cx: number;
  cy: number;
  w?: number;
  h?: number;
  color: string;
  bgColor: string;
  revealFrame: number;
}

interface EdgeDef {
  from: string;
  to: string;
  dashed?: boolean;
  label?: string;
  forceVertical?: boolean;
  bidirectional?: boolean;
}

interface SectionDef {
  id: string;
  label: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color: string;
  bgColor: string;
  revealFrame: number;
}

interface EdgeGeom {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

// ── Color roles — matches reference image color coding ────────────────────────
const COL = {
  io:        { color: "#94a3b8", bgColor: "#0d1520" }, // gray — Voice/Text/Device
  agent:     { color: "#60a5fa", bgColor: "#0a1a2e" }, // blue — process agents
  router:    { color: "#fb923c", bgColor: "#1a0900" }, // orange — validators/routers
  retry:     { color: "#f87171", bgColor: "#1a0505" }, // red — retry/error
  responder: { color: "#f472b6", bgColor: "#1a0515" }, // pink — TTS/responder
  success:   { color: "#4ade80", bgColor: "#05180a" }, // green — END/success
};

// ── Sections ──────────────────────────────────────────────────────────────────
const SECTIONS: SectionDef[] = [
  {
    id: "input",
    label: "Input Layer",
    x1: 28, y1: 50, x2: W - 28, y2: 222,
    color: "#3b82f6",
    bgColor: "rgba(30,58,138,0.16)",
    revealFrame: 45,
  },
  {
    id: "orchestration",
    label: "Orchestration Layer — LangGraph (15 Nodes)",
    x1: 28, y1: 238, x2: W - 28, y2: 715,
    color: "#818cf8",
    bgColor: "rgba(49,46,129,0.16)",
    revealFrame: 162,
  },
  {
    id: "execution",
    label: "Execution Layer",
    x1: 28, y1: 732, x2: W - 28, y2: 1055,
    color: "#22c55e",
    bgColor: "rgba(20,83,45,0.16)",
    revealFrame: 418,
  },
];

// ── Nodes — serpentine reveal following actual pipeline flow ──────────────────
const NODES: NodeDef[] = [
  // ── INPUT LAYER ─────────────────────────────────────────────────────────────
  {
    id: "voice",
    label: "Voice Input",
    sub: "WebSocket stream",
    cx: 250, cy: 120,
    ...COL.io,
    revealFrame: 65,
  },
  {
    id: "text",
    label: "Text Input",
    sub: "REST API",
    cx: 250, cy: 180,
    w: 195, h: 50,
    ...COL.io,
    revealFrame: 65,
  },
  {
    id: "stt",
    label: "STT",
    sub: "Whisper v3 Turbo",
    cx: 650, cy: 120,
    ...COL.agent,
    revealFrame: 98,
  },
  {
    id: "commander",
    label: "CommanderAgent",
    sub: "Intent Parsing",
    cx: 1120, cy: 120,
    w: 264,
    ...COL.agent,
    revealFrame: 135,
  },

  // ── ORCHESTRATION — TOP ──────────────────────────────────────────────────────
  {
    id: "validator",
    label: "ValidatorAgent",
    sub: "Rule pre-checks",
    cx: 430, cy: 318,
    ...COL.router,
    revealFrame: 192,
  },
  {
    id: "edge-router",
    label: "Edge Router",
    sub: "Conditional branch",
    cx: 760, cy: 318,
    ...COL.router,
    revealFrame: 235,
  },

  // ── BRANCH A — conv. ─────────────────────────────────────────────────────────
  {
    id: "speak",
    label: "speak",
    sub: "TTS response",
    cx: 215, cy: 452,
    w: 178,
    ...COL.responder,
    revealFrame: 278,
  },
  {
    id: "end-node",
    label: "END",
    sub: "",
    cx: 215, cy: 548,
    w: 138, h: 50,
    ...COL.success,
    revealFrame: 312,
  },

  // ── BRANCH B — UI action ──────────────────────────────────────────────────────
  {
    id: "perception",
    label: "perception",
    sub: "annotation path",
    cx: 760, cy: 428,
    ...COL.agent,
    revealFrame: 278,
  },
  {
    id: "create-plan",
    label: "create_plan",
    sub: "step list",
    cx: 760, cy: 510,
    ...COL.agent,
    revealFrame: 312,
  },
  {
    id: "execute",
    label: "execute",
    sub: "WebSocket gesture",
    cx: 760, cy: 592,
    ...COL.agent,
    revealFrame: 348,
  },
  {
    id: "validate-outcome",
    label: "validate_outcome",
    sub: "verify result",
    cx: 760, cy: 670,
    w: 256,
    ...COL.router,
    revealFrame: 385,
  },

  // ── BRANCH C — multi-step ─────────────────────────────────────────────────────
  {
    id: "decompose",
    label: "decompose_goal",
    sub: "Planner",
    cx: 1420, cy: 428,
    w: 248,
    ...COL.agent,
    revealFrame: 278,
  },
  {
    id: "coordinator",
    label: "Coordinator",
    sub: "Reactive loop",
    cx: 1420, cy: 510,
    ...COL.router,
    revealFrame: 312,
  },
  {
    id: "next-subgoal",
    label: "next_subgoal",
    sub: "advance",
    cx: 1420, cy: 592,
    ...COL.agent,
    revealFrame: 348,
  },
  {
    id: "retry-router",
    label: "retry_router",
    sub: "5-level ladder",
    cx: 1420, cy: 670,
    w: 238,
    ...COL.retry,
    revealFrame: 385,
  },

  // ── EXECUTION LAYER ───────────────────────────────────────────────────────────
  {
    id: "perceiver",
    label: "PerceiverAgent",
    sub: "Annotation Pipeline",
    cx: 310, cy: 825,
    ...COL.success,
    revealFrame: 448,
  },
  {
    id: "planner",
    label: "PlannerAgent",
    sub: "Goal Decomposition",
    cx: 820, cy: 825,
    ...COL.agent,
    revealFrame: 448,
  },
  {
    id: "actor",
    label: "ActorAgent",
    sub: "Gesture Execution",
    cx: 310, cy: 916,
    ...COL.agent,
    revealFrame: 486,
  },
  {
    id: "verifier",
    label: "VerifierAgent",
    sub: "Outcome Check",
    cx: 820, cy: 916,
    ...COL.agent,
    revealFrame: 486,
  },
  {
    id: "responder",
    label: "ResponderAgent",
    sub: "TTS Feedback",
    cx: 310, cy: 999,
    ...COL.responder,
    revealFrame: 524,
  },
  {
    id: "android",
    label: "Android Device",
    sub: "WebSocket + ACS",
    cx: 820, cy: 999,
    ...COL.io,
    revealFrame: 524,
  },
  {
    id: "task-complete",
    label: "Task Complete",
    sub: "spoken + visual feedback",
    cx: 1350, cy: 962,
    w: 290, h: 72,
    ...COL.success,
    revealFrame: 568,
  },
];

// ── Edges ─────────────────────────────────────────────────────────────────────
const EDGES: EdgeDef[] = [
  // Input Layer
  { from: "voice",     to: "stt" },
  { from: "text",      to: "commander", dashed: true, label: "bypasses STT" },
  { from: "stt",       to: "commander" },
  // Into Orchestration
  { from: "commander", to: "validator", forceVertical: true },
  // Top of Orchestration
  { from: "validator",   to: "edge-router" },
  // Branch A — conv.
  { from: "edge-router", to: "speak",    label: "conv." },
  { from: "speak",       to: "end-node" },
  // Branch B — UI action
  { from: "edge-router", to: "perception",       label: "UI action", forceVertical: true },
  { from: "perception",  to: "create-plan" },
  { from: "create-plan", to: "execute" },
  { from: "execute",     to: "validate-outcome" },
  // Branch C — multi-step
  { from: "edge-router", to: "decompose",  label: "multi-step" },
  { from: "decompose",   to: "coordinator" },
  { from: "coordinator", to: "next-subgoal" },
  { from: "next-subgoal",to: "retry-router" },
  // Into Execution (feedback loop, dashed)
  { from: "validate-outcome", to: "perceiver", dashed: true, forceVertical: true },
  // Execution Layer
  { from: "perceiver", to: "planner",  bidirectional: true },
  { from: "perceiver", to: "actor" },
  { from: "planner",   to: "verifier" },
  { from: "actor",     to: "verifier" },
  { from: "actor",     to: "responder" },
  { from: "verifier",  to: "android" },
  { from: "responder", to: "android" },
  { from: "android",   to: "task-complete" },
];

// ── Branch labels ─────────────────────────────────────────────────────────────
const BRANCH_LABELS = [
  { text: "conv.",      x: 215,  y: 395, revealFrame: 260 },
  { text: "UI action",  x: 760,  y: 388, revealFrame: 260 },
  { text: "multi-step", x: 1420, y: 388, revealFrame: 260 },
];

// ── Geometry helpers ──────────────────────────────────────────────────────────
const nodeMap = new Map<string, NodeDef>(NODES.map((n) => [n.id, n]));

function nw(n: NodeDef) {
  return n.w ?? NODE_W;
}
function nh(n: NodeDef) {
  return n.h ?? NODE_H;
}

function getEdgeGeom(from: NodeDef, to: NodeDef, forceVertical?: boolean): EdgeGeom {
  const dx = to.cx - from.cx;
  const dy = to.cy - from.cy;

  if (forceVertical || Math.abs(dy) >= Math.abs(dx)) {
    const sy = Math.sign(dy === 0 ? 1 : dy);
    return {
      x1: from.cx,
      y1: from.cy + sy * (nh(from) / 2),
      x2: to.cx,
      y2: to.cy - sy * (nh(to) / 2),
    };
  }
  const sx = Math.sign(dx === 0 ? 1 : dx);
  return {
    x1: from.cx + sx * (nw(from) / 2),
    y1: from.cy,
    x2: to.cx - sx * (nw(to) / 2),
    y2: to.cy,
  };
}

// ── Dot-grid background ───────────────────────────────────────────────────────
const GridDots: React.FC = () => {
  const cols = Math.ceil(W / 55) + 1;
  const rows = Math.ceil(H / 55) + 1;
  const dots: React.ReactNode[] = [];
  for (let xi = 0; xi < cols; xi++) {
    for (let yi = 0; yi < rows; yi++) {
      dots.push(
        <circle key={`${xi}-${yi}`} cx={xi * 55} cy={yi * 55} r={1.1} fill="#fff" opacity={0.055} />
      );
    }
  }
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {dots}
    </svg>
  );
};

// ── Main composition ──────────────────────────────────────────────────────────
export const ArchDiagram: React.FC = () => {
  const frame = useCurrentFrame();

  // Compute edge data (geometry + reveal timing)
  const edgesComputed = EDGES.flatMap((edge) => {
    const from = nodeMap.get(edge.from);
    const to = nodeMap.get(edge.to);
    if (!from || !to) return [];

    const geom = getEdgeGeom(from, to, edge.forceVertical);
    const revealFrame = Math.max(from.revealFrame, to.revealFrame);
    const edgeColor = edge.dashed ? "rgba(255,255,255,0.3)" : from.color;

    const result = [{ edge, from, to, geom, revealFrame, edgeColor, reverse: false }];

    if (edge.bidirectional) {
      // Second arrow: reversed direction, slight offset
      const geomRev = getEdgeGeom(to, from, edge.forceVertical);
      // Offset both lines by ±5px perpendicular to avoid overlap
      const dx = geom.x2 - geom.x1;
      const dy = geom.y2 - geom.y1;
      const len = Math.hypot(dx, dy) || 1;
      const ox = (-dy / len) * 5;
      const oy = (dx / len) * 5;
      result[0] = {
        ...result[0],
        geom: { x1: geom.x1 + ox, y1: geom.y1 + oy, x2: geom.x2 + ox, y2: geom.y2 + oy },
      };
      result.push({
        edge,
        from: to,
        to: from,
        geom: { x1: geomRev.x1 - ox, y1: geomRev.y1 - oy, x2: geomRev.x2 - ox, y2: geomRev.y2 - oy },
        revealFrame,
        edgeColor: to.color,
        reverse: true,
      });
    }
    return result;
  });

  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(ellipse at 48% 45%, #080822 0%, #020208 100%)",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        overflow: "hidden",
      }}
    >
      {/* ── 1. Dot grid ── */}
      <GridDots />

      {/* ── 2. Scanlines ── */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.05) 3px, rgba(0,0,0,0.05) 4px)",
          pointerEvents: "none",
        }}
      />

      {/* ── 3. Section boxes ── */}
      {SECTIONS.map((sec) => {
        const opacity = interpolate(frame, [sec.revealFrame, sec.revealFrame + 18], [0, 1], {
          extrapolateRight: "clamp",
        });
        const scl = interpolate(frame, [sec.revealFrame, sec.revealFrame + 18], [0.985, 1], {
          extrapolateRight: "clamp",
        });
        return (
          <div
            key={sec.id}
            style={{
              position: "absolute",
              left: sec.x1,
              top: sec.y1,
              width: sec.x2 - sec.x1,
              height: sec.y2 - sec.y1,
              opacity,
              transform: `scale(${scl})`,
              transformOrigin: "center",
              border: `1px solid ${sec.color}44`,
              borderRadius: 10,
              background: sec.bgColor,
            }}
          >
            {/* Section header accent line */}
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: 28,
                borderBottom: `1px solid ${sec.color}22`,
                borderRadius: "10px 10px 0 0",
                background: `${sec.color}0d`,
                display: "flex",
                alignItems: "center",
                paddingLeft: 14,
                gap: 8,
              }}
            >
              {/* Color dot */}
              <div
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: sec.color,
                  boxShadow: `0 0 6px ${sec.color}`,
                }}
              />
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: sec.color,
                  letterSpacing: 2,
                  textTransform: "uppercase",
                }}
              >
                {sec.label}
              </span>
            </div>
          </div>
        );
      })}

      {/* ── 4. SVG edges + particles ── */}
      <svg width={W} height={H} style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
        <defs>
          <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="3.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="particle-glow" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          {/* Arrow marker — orient auto so it rotates with line direction */}
          <marker id="arrow" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto">
            <polygon points="0 0, 9 3.5, 0 7" fill="rgba(255,255,255,0.8)" />
          </marker>
          <marker id="arrow-dim" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
            <polygon points="0 0, 7 3, 0 6" fill="rgba(255,255,255,0.3)" />
          </marker>
        </defs>

        {edgesComputed.map((item, ei) => {
          if (frame < item.revealFrame) return null;

          const { geom, edgeColor, edge } = item;
          const drawDuration = edge.dashed ? 25 : 42;
          const progress = interpolate(
            frame,
            [item.revealFrame, item.revealFrame + drawDuration],
            [0, 1],
            { extrapolateRight: "clamp" }
          );

          const tipX = geom.x1 + (geom.x2 - geom.x1) * progress;
          const tipY = geom.y1 + (geom.y2 - geom.y1) * progress;
          const isComplete = progress >= 1;

          // Traveling data-flow particle
          const particleT =
            isComplete ? ((frame - (item.revealFrame + drawDuration)) % 80) / 80 : null;
          const px = particleT !== null ? geom.x1 + (geom.x2 - geom.x1) * particleT : 0;
          const py = particleT !== null ? geom.y1 + (geom.y2 - geom.y1) * particleT : 0;

          return (
            <g key={`${ei}-${item.reverse}`}>
              {/* Dim rail once fully drawn */}
              {isComplete && !edge.dashed && (
                <line
                  x1={geom.x1} y1={geom.y1}
                  x2={geom.x2} y2={geom.y2}
                  stroke={edgeColor}
                  strokeWidth={1.2}
                  opacity={0.18}
                />
              )}

              {/* Main animated line */}
              {edge.dashed ? (
                <line
                  x1={geom.x1} y1={geom.y1}
                  x2={geom.x2} y2={geom.y2}
                  stroke={edgeColor}
                  strokeWidth={1.5}
                  strokeDasharray="8 6"
                  opacity={progress}
                  markerEnd="url(#arrow-dim)"
                />
              ) : (
                <line
                  x1={geom.x1} y1={geom.y1}
                  x2={tipX} y2={tipY}
                  stroke={edgeColor}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  filter="url(#glow)"
                  markerEnd="url(#arrow)"
                />
              )}

              {/* Edge label */}
              {edge.label && isComplete && (
                <text
                  x={(geom.x1 + geom.x2) / 2}
                  y={(geom.y1 + geom.y2) / 2 - 9}
                  fill="rgba(255,255,255,0.55)"
                  fontSize={10}
                  textAnchor="middle"
                  fontStyle="italic"
                  fontFamily="'Segoe UI', sans-serif"
                >
                  {edge.label}
                </text>
              )}

              {/* Traveling particle (only on main solid edges) */}
              {!edge.dashed && particleT !== null && (
                <circle
                  cx={px} cy={py}
                  r={5}
                  fill={edgeColor}
                  opacity={0.85}
                  filter="url(#particle-glow)"
                />
              )}
            </g>
          );
        })}
      </svg>

      {/* ── 5. Branch column labels ── */}
      {BRANCH_LABELS.map((bl) => {
        const opacity = interpolate(frame, [bl.revealFrame, bl.revealFrame + 18], [0, 1], {
          extrapolateRight: "clamp",
        });
        return (
          <div
            key={bl.text}
            style={{
              position: "absolute",
              left: bl.x - 40,
              top: bl.y,
              width: 80,
              textAlign: "center",
              opacity,
              fontSize: 10,
              fontStyle: "italic",
              color: "rgba(255,255,255,0.4)",
              letterSpacing: 1,
            }}
          >
            {bl.text}
          </div>
        );
      })}

      {/* ── 6. Node boxes ── */}
      {NODES.map((node) => {
        if (frame < node.revealFrame) return null;

        const localFrame = frame - node.revealFrame;
        const nodeW = nw(node);
        const nodeH = nh(node);

        const opacity = interpolate(localFrame, [0, 10], [0, 1], { extrapolateRight: "clamp" });
        const scale = spring({
          frame: localFrame,
          fps: FPS,
          config: { damping: 15, stiffness: 270 },
          from: 0.45,
          to: 1.0,
        });
        // Burst glow fades to resting glow over ~40 frames
        const glowMult = interpolate(localFrame, [0, 18, 40], [2.8, 1.6, 1.0], {
          extrapolateRight: "clamp",
        });

        return (
          <div
            key={node.id}
            style={{
              position: "absolute",
              left: node.cx - nodeW / 2,
              top: node.cy - nodeH / 2,
              width: nodeW,
              height: nodeH,
              opacity,
              transform: `scale(${scale})`,
              transformOrigin: "center",
              display: "flex",
              alignItems: "stretch",
              background: node.bgColor,
              border: `1px solid ${node.color}55`,
              borderRadius: 7,
              overflow: "hidden",
              boxShadow: [
                `0 0 ${16 * glowMult}px ${node.color}66`,
                `0 0 ${36 * glowMult}px ${node.color}28`,
                "0 2px 10px rgba(0,0,0,0.65)",
                "inset 0 1px 0 rgba(255,255,255,0.05)",
              ].join(", "),
            }}
          >
            {/* Left color accent bar */}
            <div
              style={{
                width: 4,
                flexShrink: 0,
                background: `linear-gradient(180deg, ${node.color} 0%, ${node.color}88 100%)`,
              }}
            />
            {/* Text content */}
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
                paddingLeft: 11,
                paddingRight: 8,
                gap: 2,
              }}
            >
              <span
                style={{
                  fontSize: 13,
                  fontWeight: 700,
                  color: node.color,
                  letterSpacing: 0.3,
                  lineHeight: 1.25,
                  textShadow: `0 0 10px ${node.color}66`,
                }}
              >
                {node.label}
              </span>
              {node.sub && (
                <span
                  style={{
                    fontSize: 10,
                    color: "rgba(255,255,255,0.38)",
                    fontFamily: "'Courier New', monospace",
                    letterSpacing: 0.1,
                    lineHeight: 1.3,
                  }}
                >
                  {node.sub}
                </span>
              )}
            </div>
          </div>
        );
      })}

      {/* ── 7. Title bar ── */}
      {(() => {
        const opacity = interpolate(frame, [0, 22], [0, 1], { extrapolateRight: "clamp" });
        const y = interpolate(frame, [0, 25], [-14, 0], { extrapolateRight: "clamp" });
        return (
          <div
            style={{
              position: "absolute",
              top: 14,
              left: 0,
              right: 0,
              textAlign: "center",
              opacity,
              transform: `translateY(${y}px)`,
              pointerEvents: "none",
            }}
          >
            <span
              style={{
                fontSize: 22,
                fontWeight: 800,
                letterSpacing: 6,
                background: "linear-gradient(90deg, #a78bfa 0%, #60a5fa 45%, #22d3ee 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              AURA — SYSTEM ARCHITECTURE
            </span>
            <span
              style={{
                display: "block",
                marginTop: 3,
                fontSize: 10,
                color: "rgba(255,255,255,0.25)",
                letterSpacing: 4,
              }}
            >
              AUTONOMOUS USER-RESPONSIVE AGENT · GEMINI LIVE HACKATHON 2026
            </span>
          </div>
        );
      })()}

      {/* ── 8. Footer ── */}
      <div
        style={{
          position: "absolute",
          bottom: 12,
          left: 0,
          right: 0,
          textAlign: "center",
          fontSize: 9,
          color: "rgba(255,255,255,0.15)",
          letterSpacing: 3,
          pointerEvents: "none",
        }}
      >
        GEMINI LIVE · LANGGRAPH · YOLOV8 · OPA REGO · GROQ WHISPER · EDGE-TTS · GOOGLE CLOUD RUN
      </div>
    </AbsoluteFill>
  );
};
