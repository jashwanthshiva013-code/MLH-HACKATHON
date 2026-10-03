import { useState } from 'react';
import RateLimitPill from './RateLimitPill.jsx';

const EXAMPLES = [
  { label: 'Add login page', text: 'This website does not have a login page. I need to add a login page.' },
  { label: 'Fix authentication bug', text: 'Login fails when the token expires. Users get logged out unexpectedly.' },
  { label: 'Add dark mode', text: 'Add a dark mode toggle to the website.' },
  { label: 'Improve API error handling', text: 'API errors are not handled gracefully. Improve error handling and show friendly messages.' },
];

export default function Landing({ onAnalyze, onDemo }) {
  const [repoUrl, setRepoUrl] = useState('');
  const [issue, setIssue] = useState('');
  const [formError, setFormError] = useState('');

  const submit = (e) => {
    e.preventDefault();
    if (!repoUrl.trim() || !issue.trim()) {
      setFormError('Please enter both a repository URL and an issue description.');
      return;
    }
    setFormError('');
    onAnalyze(repoUrl.trim(), issue.trim().split('\n')[0].slice(0, 120), issue.trim());
  };

  return (
    <div>
      <nav className="nav">
        <div className="nav-inner">
          <a className="brand" href="#" onClick={(e) => { e.preventDefault(); window.scrollTo(0, 0); }}>
            <span className="brand-mark">CG</span> ContribGuide AI
          </a>
          <div className="nav-links">
            <a href="#analyze">Repository</a>
            <a href="#how">How it works</a>
            <a href="#about">About</a>
          </div>
          <RateLimitPill />
        </div>
      </nav>

      <header className="hero">
        <h1>From GitHub Issue to Contribution&nbsp;Plan.</h1>
        <p className="subtitle">
          Understand unfamiliar open-source codebases, find the files that matter,
          and get an evidence-backed step-by-step guide for your first contribution.
        </p>
        <a className="btn btn-primary btn-lg" href="#analyze">Analyze a Repository</a>
        <p className="hero-note">AI guides you. You write the code.</p>
      </header>

      <main className="container">
        <section id="analyze" className="card analyze-card">
          <h2>Analyze a repository</h2>
          <form onSubmit={submit}>
            <label>
              GitHub Repository URL
              <input
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/username/project"
              />
            </label>
            <label>
              GitHub Issue
              <textarea
                value={issue}
                onChange={(e) => setIssue(e.target.value)}
                rows={4}
                placeholder="Describe the bug, feature request, or issue…"
              />
            </label>
            {formError && <div className="alert alert-error">{formError}</div>}
            <button className="btn btn-primary" type="submit">Analyze Issue</button>
          </form>
          <div className="examples">
            <span className="muted">Try an example:</span>
            {EXAMPLES.map((ex) => (
              <button key={ex.label} type="button" className="chip" onClick={() => setIssue(ex.text)}>
                {ex.label}
              </button>
            ))}
          </div>
          <div className="demo-row">
            <span className="muted">No repo handy?</span>
            <button type="button" className="btn btn-ghost" onClick={() => onDemo('bug')}>
              Demo: bug fix (offline)
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => onDemo('feature')}>
              Demo: feature request (offline)
            </button>
          </div>
          <p className="muted small">Public repositories only. Nothing is stored — the AI guides you, it never modifies your code.</p>
        </section>

        <section id="how" className="how">
          <h2>How it works</h2>
          <div className="how-grid">
            <div className="how-step"><div className="how-num">1</div><h3>Paste a repo + issue</h3><p>You provide a public GitHub repository URL and the issue you want to work on.</p></div>
            <div className="how-step"><div className="how-num">2</div><h3>AI scans the repository</h3><p>The analyzer maps the project structure, finds relevant files, and traces how they connect.</p></div>
            <div className="how-step"><div className="how-num">3</div><h3>Get an evidence-backed plan</h3><p>Every recommendation cites actual code — with confidence levels and confirmed-vs-suggested labels.</p></div>
            <div className="how-step"><div className="how-num">4</div><h3>You contribute</h3><p>Follow the step-by-step plan, write the tests, and open your pull request with confidence.</p></div>
          </div>
        </section>

        <section id="about" className="card about">
          <h2>About</h2>
          <h3>Problem</h3>
          <p>New contributors often struggle to understand unfamiliar repositories and translate GitHub issues into concrete development tasks.</p>
          <h3>Solution</h3>
          <p>ContribGuide AI analyzes a repository together with a specific issue and generates an evidence-grounded contribution plan.</p>
          <h3>AI contribution</h3>
          <p>The open-weight AI identifies relevant code, explains relationships, proposes implementation steps, and creates a test plan — every claim backed by repository evidence.</p>
          <h3>Important</h3>
          <p>The AI does not modify the repository automatically. It guides you; you write the code.</p>
        </section>
      </main>

      <footer className="footer">
        ContribGuide AI · Evidence-Grounded AI Contribution Guide · Built for MLH × DEV × React Hyderabad Hack Day
      </footer>
    </div>
  );
}
