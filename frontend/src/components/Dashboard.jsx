import { Fragment, useState } from 'react';
import { refinePlan } from '../services/api.js';
import RateLimitPill from './RateLimitPill.jsx';

const TOC = [
  ['issue', 'Issue Understanding'],
  ['overview', 'Repository Overview'],
  ['files', 'Relevant Files'],
  ['flow', 'Code Flow'],
  ['start', 'Where to Start'],
  ['steps', 'Step-by-Step Plan'],
  ['tests', 'Test Plan'],
  ['risks', 'Potential Impact'],
  ['learning', 'Learning Path'],
  ['refine', 'Refine Plan'],
];

const TYPE_LABELS = { bug: 'Bug', feature: 'Feature', enhancement: 'Enhancement', documentation: 'Documentation', unknown: 'Unknown' };

const REFINE_SUGGESTIONS = [
  'Explain step 3',
  'Why do I need this file?',
  'Give me a simpler approach',
  'What should I learn before doing this?',
  'What tests should I write?',
];

function ConfidenceBadge({ level }) {
  return <span className={`conf conf-${level}`}>{level} confidence</span>;
}

function BasisTag({ basis }) {
  return basis === 'confirmed'
    ? <span className="tag tag-confirmed">Confirmed from repository</span>
    : <span className="tag tag-suggestion">AI suggestion</span>;
}

function Section({ id, title, children, prominent }) {
  return (
    <section id={id} className={`card section${prominent ? ' prominent' : ''}`}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export default function Dashboard({ plan, onBack }) {
  const [question, setQuestion] = useState('');
  const [qa, setQa] = useState([]);
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState('');

  const ask = async (q) => {
    const text = (q || question).trim();
    if (!text || refining) return;
    setRefining(true);
    setRefineError('');
    setQuestion('');
    try {
      const { answer } = await refinePlan(plan, text);
      setQa((prev) => [...prev, { q: text, a: answer }]);
    } catch (e) {
      setRefineError(e.message || 'Could not answer that.');
    } finally {
      setRefining(false);
    }
  };

  const ov = plan.repository_overview || {};
  const issue = plan.issue_understanding || {};

  return (
    <div>
      <nav className="nav">
        <div className="nav-inner">
          <button className="brand brand-btn" onClick={onBack}>
            <span className="brand-mark">CG</span> ContribGuide AI
          </button>
          <div className="dash-nav-right">
            <RateLimitPill />
            <span className="generated-by">{plan.generated_by}</span>
          </div>
        </div>
      </nav>

      <div className="dashboard">
        <aside className="toc">
          <div className="toc-inner">
            <strong>Contents</strong>
            {TOC.map(([id, label]) => (
              <a key={id} href={`#${id}`}>{label}</a>
            ))}
            <button className="btn btn-ghost btn-sm" onClick={onBack}>← New analysis</button>
          </div>
        </aside>

        <main className="dash-main">
          <header className="dash-header">
            <h1>Your contribution plan</h1>
            <p className="muted">{ov.name} · {ov.files_scanned} files scanned</p>
          </header>

          {plan.warnings && plan.warnings.length > 0 && (
            <div className="alert alert-warn">
              {plan.warnings.map((w, i) => <p key={i}>{w}</p>)}
            </div>
          )}

          <Section id="issue" title="Issue Understanding">
            <p className="issue-title">{issue.title}</p>
            {issue.description && <p className="muted">{issue.description}</p>}
            <p><span className="type-badge">{TYPE_LABELS[issue.type] || issue.type}</span></p>
            <p><strong>What this issue means:</strong> {issue.explanation}</p>
          </Section>

          <Section id="overview" title="Repository Overview">
            <div className="stat-grid">
              <div className="stat"><span className="stat-label">Repository</span><span className="stat-value mono">{ov.name}</span></div>
              <div className="stat"><span className="stat-label">Primary language</span><span className="stat-value">{ov.language}</span></div>
              <div className="stat"><span className="stat-label">Framework</span><span className="stat-value">{ov.framework}</span></div>
              <div className="stat"><span className="stat-label">Files scanned</span><span className="stat-value">{ov.files_scanned}</span></div>
            </div>
            {ov.folders && ov.folders.length > 0 && (
              <p><strong>Important folders:</strong> {ov.folders.map((f) => <code key={f} className="folder">{f}/</code>).reduce((a, b) => <>{a} {b}</>)}</p>
            )}
          </Section>

          <Section id="files" title="Relevant Files">
            {plan.relevant_files.length === 0 && (
              <p className="muted">No relevant files were confidently identified for this issue.</p>
            )}
            {plan.relevant_files.map((f) => (
              <div className="file" key={f.path}>
                <div className="file-head">
                  <span className="file-path">✓ {f.path}</span>
                  <ConfidenceBadge level={f.confidence} />
                </div>
                <p><strong>Why relevant:</strong> {f.reason}</p>
                {f.evidence_summary && <p className="muted"><strong>Evidence:</strong> {f.evidence_summary}</p>}
                {f.evidence && f.evidence.length > 0 && (
                  <div className="evidence">
                    {f.evidence.map((e, i) => (
                      <div className="ev-line" key={i}>
                        <span className="ev-loc">{f.path}:{e.line}</span>
                        <code>{e.text}</code>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </Section>

          <Section id="flow" title="Code Flow">
            {plan.flow && plan.flow.length > 0 ? (
              <Fragment>
                <div className="flow">
                  {plan.flow.map((p, i) => (
                    <Fragment key={p}>
                      <div className="node">{p}</div>
                      {i < plan.flow.length - 1 && <div className="arrow">↓</div>}
                    </Fragment>
                  ))}
                </div>
                <p className="muted small">Only relationships found by reading the code are shown — nothing is invented.</p>
              </Fragment>
            ) : (
              <p className="muted">{plan.flow_note || 'Flow could not be fully established from the scanned files.'}</p>
            )}
          </Section>

          {plan.starting_point && (
            <Section id="start" title="Where to Start">
              <div className="start-card">
                <div className="start-label">START HERE</div>
                <div className="file-path big">{plan.starting_point.file}</div>
                <p><strong>Why?</strong> {plan.starting_point.reason}</p>
              </div>
            </Section>
          )}

          <Section id="steps" title="Step-by-Step Contribution Plan" prominent>
            <ol className="steps">
              {plan.steps.map((s, i) => (
                <li key={i}>
                  <div className="step-text">{s.text}</div>
                  <BasisTag basis={s.basis} />
                </li>
              ))}
            </ol>
          </Section>

          <Section id="tests" title="Test Plan">
            {plan.tests.checklist && plan.tests.checklist.length > 0 && (
              <Fragment>
                <p><strong>What to verify:</strong></p>
                <ul className="checklist">
                  {plan.tests.checklist.map((t) => <li key={t}>✓ {t}</li>)}
                </ul>
              </Fragment>
            )}
            {plan.tests.existing.length > 0 && (
              <Fragment>
                <p><strong>Existing tests related to the issue:</strong></p>
                <ul>{plan.tests.existing.map((t) => <li key={t}>✓ <code>{t}</code></li>)}</ul>
              </Fragment>
            )}
            {plan.tests.suggested.length > 0 && (
              <Fragment>
                <p><strong>Suggested new tests:</strong></p>
                <ul className="checklist">
                  {plan.tests.suggested.map((t) => <li key={t}>✓ {t}</li>)}
                </ul>
              </Fragment>
            )}
            {plan.tests.note && <p className="muted">{plan.tests.note}</p>}
          </Section>

          <Section id="risks" title="Potential Impact / Risks">
            <div className="risk-chips">
              {plan.risks.map((r, i) => (
                <span key={i} className="risk-chip">
                  {r.area} <BasisTag basis={r.basis} />
                </span>
              ))}
            </div>
          </Section>

          <Section id="learning" title="Learning Path">
            <p><strong>Before working on this issue, understand:</strong></p>
            <ul>
              {(plan.learning.topics || []).map((t) => <li key={t}>{t}</li>)}
            </ul>
            {(plan.learning.reading_order || []).length > 0 && (
              <Fragment>
                <p><strong>Recommended reading order:</strong></p>
                <div className="flow flow-h">
                  {plan.learning.reading_order.map((p, i, arr) => (
                    <Fragment key={p}>
                      <div className="node small">{p}</div>
                      {i < arr.length - 1 && <div className="arrow-h">→</div>}
                    </Fragment>
                  ))}
                </div>
              </Fragment>
            )}
          </Section>

          <Section id="refine" title="Refine Plan">
            <p className="muted">Ask a follow-up — the answer uses this repository's context.</p>
            <div className="refine-chips">
              {REFINE_SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="chip" onClick={() => ask(s)} disabled={refining}>
                  {s}
                </button>
              ))}
            </div>
            <div className="refine-row">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && ask()}
                placeholder="Ask about the plan…"
                disabled={refining}
              />
              <button className="btn btn-primary" onClick={() => ask()} disabled={refining}>
                {refining ? 'Thinking…' : 'Ask'}
              </button>
            </div>
            {refineError && <div className="alert alert-error">{refineError}</div>}
            {qa.map((item, i) => (
              <div className="qa" key={i}>
                <p className="qa-q">You: {item.q}</p>
                <p className="qa-a">{item.a}</p>
              </div>
            ))}
          </Section>

          <button className="btn btn-ghost" onClick={onBack}>← Analyze another repository</button>
        </main>
      </div>

      <footer className="footer">
        ContribGuide AI · Evidence-Grounded AI Contribution Guide · The AI guides you — it never modifies your code.
      </footer>
    </div>
  );
}
