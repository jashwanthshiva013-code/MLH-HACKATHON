import { useCallback, useState } from 'react';
import Landing from './components/Landing.jsx';
import Analyzing from './components/Analyzing.jsx';
import Dashboard from './components/Dashboard.jsx';
import { analyzeRepo, getDemo } from './services/api.js';

export default function App() {
  const [view, setView] = useState('landing'); // landing | analyzing | result | error
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);
  const [analysisDone, setAnalysisDone] = useState(false);
  const [lastRequest, setLastRequest] = useState(null); // for Retry Analysis

  const startAnalysis = useCallback((request) => {
    setError(null);
    setPlan(null);
    setAnalysisDone(false);
    setLastRequest(request);
    setView('analyzing');
    const promise =
      request.type === 'demo'
        ? getDemo(request.name)
        : analyzeRepo(request.payload);
    promise.then(
      (result) => {
        setPlan(result);
        setAnalysisDone(true);
      },
      (err) => {
        // Reported honestly — no fake results are generated on failure.
        setError(err.message || 'Analysis failed.');
        setView('error');
      }
    );
  }, []);

  const handleAnalyze = useCallback(
    (repoUrl, issueTitle, issueDescription) =>
      startAnalysis({
        type: 'analyze',
        payload: { repo_url: repoUrl, issue_title: issueTitle, issue_description: issueDescription },
      }),
    [startAnalysis]
  );

  const handleDemo = useCallback(
    (name) => startAnalysis({ type: 'demo', name }),
    [startAnalysis]
  );

  const handleRetry = useCallback(() => {
    if (lastRequest) startAnalysis(lastRequest);
  }, [lastRequest, startAnalysis]);

  const goHome = useCallback(() => {
    setView('landing');
    setPlan(null);
    setError(null);
    setLastRequest(null);
  }, []);

  if (view === 'analyzing') {
    return <Analyzing done={analysisDone} onComplete={() => setView('result')} />;
  }

  if (view === 'result' && plan) {
    return <Dashboard plan={plan} onBack={goHome} />;
  }

  if (view === 'error') {
    return (
      <div className="error-wrap">
        <div className="card error-card">
          <h2>Analysis failed</h2>
          <div className="alert alert-error">{error}</div>
          <p className="muted">
            The repository could not be analyzed, so no contribution plan was
            generated. Nothing was faked — fix the issue above and try again.
          </p>
          <div className="btn-row">
            <button className="btn btn-primary" onClick={handleRetry}>
              Retry Analysis
            </button>
            <button className="btn btn-ghost" onClick={goHome}>
              Back to start
            </button>
          </div>
        </div>
      </div>
    );
  }

  return <Landing onAnalyze={handleAnalyze} onDemo={handleDemo} />;
}
