import { useEffect, useRef, useState } from 'react';

const STAGES = [
  'Connecting to repository',
  'Scanning repository',
  'Understanding project structure',
  'Finding relevant files',
  'Analyzing issue',
  'Generating contribution plan',
];

export default function Analyzing({ done, onComplete }) {
  const [stageIdx, setStageIdx] = useState(0);
  const completed = useRef(false);

  useEffect(() => {
    const timer = setInterval(() => {
      setStageIdx((i) => (i < STAGES.length - 1 ? i + 1 : i));
    }, 1100);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (done && !completed.current) {
      completed.current = true;
      setStageIdx(STAGES.length - 1);
      const t = setTimeout(onComplete, 900);
      return () => clearTimeout(t);
    }
  }, [done, onComplete]);

  return (
    <div className="analyzing-wrap">
      <div className="analyzing-card">
        <div className="spinner" aria-label="Analyzing" />
        <h2>Analyzing your repository…</h2>
        <p className="muted">This usually takes 10–30 seconds depending on the repository size.</p>
        <ul className="stages">
          {STAGES.map((stage, i) => (
            <li key={stage} className={i < stageIdx ? 'done' : i === stageIdx ? 'active' : ''}>
              <span className="stage-dot">{i < stageIdx ? '✓' : ''}</span>
              {stage}
              {i === stageIdx && <span className="pulse">…</span>}
            </li>
          ))}
        </ul>
        <div className="progress">
          <div
            className="progress-bar"
            style={{ width: `${((stageIdx + 1) / STAGES.length) * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}
