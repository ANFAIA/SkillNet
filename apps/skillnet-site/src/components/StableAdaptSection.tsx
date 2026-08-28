import {
  Activity,
  BookOpen,
  Boxes,
  FileText,
  LifeBuoy,
  MonitorPlay,
  Pause,
  PencilLine,
  Play,
} from "lucide-react";
import { motion } from "framer-motion";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type { Locale } from "../i18n/config";
import { t, type Copy } from "../i18n/ui";
import { revealGroup, revealItem, useEntrance } from "./useEntrance";

type VisionCopy = Copy["vision"];

const LEARNING_COMPONENTS = [
  ["explanation", BookOpen],
  ["practice", PencilLine],
  ["simulation", Activity],
  ["support", LifeBuoy],
] as const;

type Point = { x: number; y: number };
type Pose = {
  hip: Point;
  leftHand: Point;
  rightHand: Point;
  leftFoot: Point;
  rightFoot: Point;
};
type PoseHandle = keyof Pose;

const INITIAL_FRAME_POSES: Pose[] = [
  { hip: { x: 210, y: 94 }, leftHand: { x: 238, y: 77 }, rightHand: { x: 184, y: 109 }, leftFoot: { x: 181, y: 148 }, rightFoot: { x: 244, y: 147 } },
  { hip: { x: 210, y: 89 }, leftHand: { x: 232, y: 91 }, rightHand: { x: 189, y: 91 }, leftFoot: { x: 196, y: 148 }, rightFoot: { x: 236, y: 137 } },
  { hip: { x: 210, y: 84 }, leftHand: { x: 219, y: 106 }, rightHand: { x: 198, y: 69 }, leftFoot: { x: 215, y: 143 }, rightFoot: { x: 235, y: 132 } },
  { hip: { x: 210, y: 89 }, leftHand: { x: 188, y: 111 }, rightHand: { x: 233, y: 75 }, leftFoot: { x: 244, y: 147 }, rightFoot: { x: 182, y: 148 } },
  { hip: { x: 210, y: 94 }, leftHand: { x: 183, y: 78 }, rightHand: { x: 237, y: 108 }, leftFoot: { x: 245, y: 148 }, rightFoot: { x: 180, y: 147 } },
  { hip: { x: 210, y: 89 }, leftHand: { x: 190, y: 91 }, rightHand: { x: 231, y: 91 }, leftFoot: { x: 235, y: 137 }, rightFoot: { x: 195, y: 148 } },
  { hip: { x: 210, y: 84 }, leftHand: { x: 198, y: 69 }, rightHand: { x: 219, y: 106 }, leftFoot: { x: 235, y: 132 }, rightFoot: { x: 214, y: 143 } },
  { hip: { x: 210, y: 89 }, leftHand: { x: 233, y: 75 }, rightHand: { x: 188, y: 111 }, leftFoot: { x: 182, y: 148 }, rightFoot: { x: 244, y: 147 } },
];

const HANDLE_LABELS: Record<PoseHandle, keyof VisionCopy> = {
  hip: "simulatorHip",
  leftHand: "simulatorLeftHand",
  rightHand: "simulatorRightHand",
  leftFoot: "simulatorLeftFoot",
  rightFoot: "simulatorRightFoot",
};

function bentJoint(start: Point, end: Point, bend: number): Point {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.max(Math.hypot(dx, dy), 1);
  return {
    x: (start.x + end.x) / 2 + (dy / length) * bend,
    y: (start.y + end.y) / 2 - (dx / length) * bend,
  };
}

function PoseFigure({ pose, className }: { pose: Pose; className: string }) {
  const shoulder = { x: pose.hip.x, y: pose.hip.y - 31 };
  const leftShoulder = { x: shoulder.x - 5, y: shoulder.y + 1 };
  const rightShoulder = { x: shoulder.x + 5, y: shoulder.y + 1 };
  const leftHip = { x: pose.hip.x - 4, y: pose.hip.y };
  const rightHip = { x: pose.hip.x + 4, y: pose.hip.y };
  const leftElbow = bentJoint(leftShoulder, pose.leftHand, 6);
  const rightElbow = bentJoint(rightShoulder, pose.rightHand, -6);
  const leftKnee = bentJoint(leftHip, pose.leftFoot, -7);
  const rightKnee = bentJoint(rightHip, pose.rightFoot, 7);

  return (
    <g className={className}>
      <circle cx={shoulder.x} cy={shoulder.y - 15} r="8" />
      <path d={`M${shoulder.x} ${shoulder.y - 7} L${pose.hip.x} ${pose.hip.y}`} />
      <path d={`M${leftShoulder.x} ${leftShoulder.y} Q${leftElbow.x} ${leftElbow.y} ${pose.leftHand.x} ${pose.leftHand.y}`} />
      <path d={`M${rightShoulder.x} ${rightShoulder.y} Q${rightElbow.x} ${rightElbow.y} ${pose.rightHand.x} ${pose.rightHand.y}`} />
      <path d={`M${leftHip.x} ${leftHip.y} Q${leftKnee.x} ${leftKnee.y} ${pose.leftFoot.x} ${pose.leftFoot.y}`} />
      <path d={`M${rightHip.x} ${rightHip.y} Q${rightKnee.x} ${rightKnee.y} ${pose.rightFoot.x} ${pose.rightFoot.y}`} />
    </g>
  );
}

function FormatTranslation({ copy }: { copy: VisionCopy }) {
  const steps = [
    { label: copy.previousFormat, icon: FileText },
    { label: copy.screenCopy, icon: MonitorPlay },
    { label: copy.ownLanguage, icon: Boxes },
  ] as const;

  return (
    <div className="vision-format" aria-label={copy.formatDiagramLabel}>
      {steps.map(({ label, icon: Icon }, index) => (
        <div className="vision-format__step" key={label}>
          <div className="vision-format__icon" aria-hidden="true"><Icon size={27} strokeWidth={1.45} /></div>
          <strong>{label}</strong>
          {index < steps.length - 1 && <span className="vision-format__arrow" aria-hidden="true">→</span>}
        </div>
      ))}
    </div>
  );
}

function CompositionSpecimens({ copy }: { copy: VisionCopy }) {
  return (
    <div className="vision-composition" aria-label={copy.compositionLabel}>
      <div className="vision-specimen vision-specimen--openui">
        <span className="vision-specimen__eyebrow"><Boxes size={17} />OpenUI</span>
        <strong>{copy.openUiDetail}</strong>
        <div className="vision-layout-sample" aria-hidden="true"><i /><i /><i /><i /></div>
      </div>

      <div className="vision-specimen vision-specimen--didact">
        <span className="vision-specimen__eyebrow"><BookOpen size={17} />Didact</span>
        <strong>{copy.didactDetail}</strong>
        <div className="vision-component-list">
          {LEARNING_COMPONENTS.map(([key, Icon]) => (
            <span key={key}><Icon size={15} />{copy[key]}</span>
          ))}
        </div>
      </div>

    </div>
  );
}

function ModelTrends({ copy }: { copy: VisionCopy }) {
  return (
    <div className="vision-trends" aria-label={copy.trendsLabel}>
      <div className="vision-trends__heading">
        <strong>{copy.trendsTitle}</strong>
        <span>{copy.moreCapableModels}</span>
      </div>
      <svg className="vision-trends__chart" viewBox="0 0 560 238" role="presentation" aria-hidden="true">
        <path className="vision-trends__axis" d="M28 202 H430" />
        <path className="vision-trends__gridline" d="M28 50 H430 M28 101 H430 M28 152 H430" />
        <path className="vision-series vision-series--personalization" d="M28 174 C115 171 148 153 208 121 S328 48 430 34" />
        <path className="vision-series vision-series--complexity" d="M28 147 C115 145 171 134 224 109 S338 68 430 60" />
        <path className="vision-series vision-series--reach" d="M28 158 C110 160 164 150 220 131 S337 92 430 83" />
        <path className="vision-series vision-series--time" d="M28 72 C110 76 158 101 220 130 S344 171 430 176" />
        <path className="vision-series vision-series--cost" d="M28 92 C100 98 153 119 218 149 S343 185 430 190" />
        <text className="vision-series-label vision-series-label--personalization" x="445" y="37">{copy.personalization}</text>
        <text className="vision-series-label" x="445" y="63">{copy.complexity}</text>
        <text className="vision-series-label vision-series-label--reach" x="445" y="86">{copy.reach}</text>
        <text className="vision-series-label vision-series-label--quiet" x="445" y="179">{copy.time}</text>
        <text className="vision-series-label vision-series-label--quiet" x="445" y="194">{copy.cost}</text>
        <text className="vision-axis-label" x="28" y="225">{copy.today}</text>
        <text className="vision-axis-label" x="344" y="225">{copy.moreCapableModels}</text>
      </svg>
    </div>
  );
}

function FrameSimulator({ copy }: { copy: VisionCopy }) {
  const [frame, setFrame] = useState(4);
  const [playing, setPlaying] = useState(false);
  const [onionSkin, setOnionSkin] = useState(true);
  const [poses, setPoses] = useState<Pose[]>(() => INITIAL_FRAME_POSES.map((pose) => ({
    hip: { ...pose.hip },
    leftHand: { ...pose.leftHand },
    rightHand: { ...pose.rightHand },
    leftFoot: { ...pose.leftFoot },
    rightFoot: { ...pose.rightFoot },
  })));
  const stageRef = useRef<SVGSVGElement>(null);
  const draggingRef = useRef<PoseHandle | null>(null);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(
      () => setFrame((current) => (current + 1) % INITIAL_FRAME_POSES.length),
      1000 / 8,
    );
    return () => window.clearInterval(timer);
  }, [playing]);

  const updateHandle = (handle: PoseHandle, point: Point) => {
    const limits = handle === "hip"
      ? { minX: 150, maxX: 270, minY: 72, maxY: 112 }
      : { minX: 28, maxX: 392, minY: 32, maxY: 148 };
    const nextPoint = {
      x: Math.min(limits.maxX, Math.max(limits.minX, point.x)),
      y: Math.min(limits.maxY, Math.max(limits.minY, point.y)),
    };
    setPoses((current) => current.map((pose, index) => (
      index === frame ? { ...pose, [handle]: nextPoint } : pose
    )));
  };

  const pointFromPointer = (event: ReactPointerEvent<SVGSVGElement>): Point | null => {
    const stage = stageRef.current;
    if (!stage) return null;
    const bounds = stage.getBoundingClientRect();
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * 420,
      y: ((event.clientY - bounds.top) / bounds.height) * 176,
    };
  };

  const beginDrag = (event: ReactPointerEvent<SVGGElement>, handle: PoseHandle) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    draggingRef.current = handle;
    setPlaying(false);
  };

  const moveDrag = (event: ReactPointerEvent<SVGSVGElement>) => {
    const handle = draggingRef.current;
    if (!handle) return;
    const point = pointFromPointer(event);
    if (point) updateHandle(handle, point);
  };

  const moveWithKeyboard = (event: ReactKeyboardEvent<SVGGElement>, handle: PoseHandle) => {
    const movement: Record<string, Point> = {
      ArrowLeft: { x: -1, y: 0 },
      ArrowRight: { x: 1, y: 0 },
      ArrowUp: { x: 0, y: -1 },
      ArrowDown: { x: 0, y: 1 },
    };
    const direction = movement[event.key];
    if (!direction) return;
    event.preventDefault();
    setPlaying(false);
    const step = event.shiftKey ? 6 : 2;
    const current = poses[frame][handle];
    updateHandle(handle, { x: current.x + direction.x * step, y: current.y + direction.y * step });
  };

  const activePose = poses[frame];
  const handles = Object.keys(HANDLE_LABELS) as PoseHandle[];

  return (
    <div className="vision-simulator" role="group" aria-label={copy.simulatorLabel}>
      <div className="vision-simulator__head">
        <div><strong>{copy.simulatorTitle}</strong><span>{copy.simulatorInstruction}</span></div>
        <span className="vision-simulator__fps">8 fps</span>
      </div>
      <span className="vision-simulator__status" aria-live={playing ? "off" : "polite"} aria-atomic="true">
        {copy.simulatorTitle}: {frame + 1} / {poses.length}
      </span>
      <svg
        ref={stageRef}
        className="vision-simulator__stage"
        viewBox="0 0 420 176"
        role="group"
        aria-label={copy.simulatorInstruction}
        onPointerMove={moveDrag}
        onPointerUp={() => { draggingRef.current = null; }}
        onPointerCancel={() => { draggingRef.current = null; }}
      >
        <path className="vision-simulator__ground" d="M24 148 H396" />
        {onionSkin && (
          <PoseFigure
            className="vision-pose vision-pose--ghost"
            pose={poses[(frame - 1 + poses.length) % poses.length]}
          />
        )}
        <ellipse className="vision-simulator__shadow" cx={activePose.hip.x} cy="149" rx="27" ry="3" />
        <PoseFigure className="vision-pose vision-pose--current" pose={activePose} />
        {!playing && handles.map((handle) => {
          const point = activePose[handle];
          return (
            <g
              className={`vision-simulator__handle vision-simulator__handle--${handle}`}
              role="button"
              tabIndex={0}
              aria-label={copy[HANDLE_LABELS[handle]] as string}
              onPointerDown={(event) => beginDrag(event, handle)}
              onKeyDown={(event) => moveWithKeyboard(event, handle)}
              key={handle}
            >
              <circle className="vision-simulator__handle-hit" cx={point.x} cy={point.y} r="13" />
              <circle className="vision-simulator__handle-dot" cx={point.x} cy={point.y} r={handle === "hip" ? 5 : 4} />
            </g>
          );
        })}
      </svg>
      <div className="vision-simulator__toolbar">
        <button type="button" className="vision-simulator__play" onClick={() => setPlaying((value) => !value)} aria-label={playing ? copy.pauseLabel : copy.playLabel}>
          {playing ? <Pause size={14} fill="currentColor" /> : <Play size={14} fill="currentColor" />}
        </button>
        <div className="vision-simulator__frames" role="group" aria-label={copy.simulatorDetail}>
          {poses.map((_, index) => (
            <button
              type="button"
              className={index === frame ? "is-current" : ""}
              onClick={() => { setFrame(index); setPlaying(false); }}
              aria-current={index === frame ? "step" : undefined}
              aria-label={`${copy.simulatorTitle}: ${index + 1} / ${poses.length}`}
              key={index}
            >
              <span aria-hidden="true">{index + 1}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          className={`vision-simulator__onion ${onionSkin ? "is-active" : ""}`}
          onClick={() => setOnionSkin((value) => !value)}
          aria-pressed={onionSkin}
        >
          {copy.onionSkin}
        </button>
      </div>
    </div>
  );
}

export default function StableAdaptSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).vision;
  const { ref, state } = useEntrance<HTMLDivElement>(0.14);

  return (
    <section id="vision" data-nav-theme="light" className="education-section w-full scroll-mt-24 bg-white px-6 py-20 sm:px-10 sm:py-28">
      <motion.div ref={ref} initial={false} animate={state} variants={revealGroup} className="vision-shell mx-auto w-full">
        <motion.h2 variants={revealItem} className="type-section-title">{copy.title}</motion.h2>
        <motion.p variants={revealItem} className="education-copy vision-intro">{copy.body1}</motion.p>
        <motion.div variants={revealItem} className="vision-block vision-block--full"><FormatTranslation copy={copy} /></motion.div>

        <motion.div variants={revealItem} className="vision-block vision-block--split vision-block--composition">
          <CompositionSpecimens copy={copy} />
          <p className="education-copy">{copy.body2}</p>
        </motion.div>

        <motion.div variants={revealItem} className="vision-block vision-block--split vision-block--future">
          <p className="education-copy">{copy.body3}</p>
          <ModelTrends copy={copy} />
        </motion.div>

        <motion.div variants={revealItem} className="vision-block vision-block--split vision-block--simulator">
          <FrameSimulator copy={copy} />
          <p className="education-copy">{copy.body4}</p>
        </motion.div>
      </motion.div>
    </section>
  );
}
