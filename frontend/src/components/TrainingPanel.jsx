import { useState, useEffect, useRef, useCallback } from 'react';

const LABELS = ['good', 'slouch', 'forward_head'];
const LABEL_NAMES = { good: 'Good', slouch: 'Slouch', forward_head: 'Forward Head' };

const STATUS_POLL_INTERVAL = 2000;

// ── Spinner ───────────────────────────────────────────────────────────────────
function Spinner() {
  return (
    <span style={{
      display: 'inline-block',
      width: '14px',
      height: '14px',
      border: '2px solid rgba(255,255,255,0.4)',
      borderTopColor: '#fff',
      borderRadius: '50%',
      animation: 'spin 0.7s linear infinite',
      verticalAlign: 'middle',
    }} />
  );
}

// ── Model card ────────────────────────────────────────────────────────────────
function ModelResultCard({ title, accuracy, f1, icon }) {
  const good = accuracy >= 0.85;
  return (
    <div style={{
      background: good ? 'var(--green-muted)' : 'var(--purple-muted)',
      borderRadius: '12px',
      padding: '14px 18px',
      border: `1px solid ${good ? 'var(--green-light)' : 'var(--purple-light)'}`,
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
    }}>
      <p style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-dark)' }}>
        {icon} {title}
      </p>
      <div style={{ display: 'flex', gap: '16px' }}>
        <div>
          <p style={{ fontSize: '0.7rem', color: 'var(--text-light)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Accuracy</p>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '1.1rem', fontWeight: 700, color: good ? 'var(--green)' : 'var(--purple)' }}>
            {(accuracy * 100).toFixed(1)}%
          </p>
        </div>
        <div>
          <p style={{ fontSize: '0.7rem', color: 'var(--text-light)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>F1 Score</p>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '1.1rem', fontWeight: 700, color: good ? 'var(--green)' : 'var(--purple)' }}>
            {f1.toFixed(3)}
          </p>
        </div>
      </div>
    </div>
  );
}

// ── TrainingPanel ─────────────────────────────────────────────────────────────
export function TrainingPanel({ modelsLoaded }) {
  const [expanded, setExpanded]         = useState(false);
  const [isTraining, setIsTraining]     = useState(false);
  const [trainingLog, setTrainingLog]   = useState([]);
  const [results, setResults]           = useState(null);
  const [isCollecting, setIsCollecting] = useState(false);
  const [selectedLabel, setSelectedLabel] = useState('good');
  const [error, setError]               = useState(null);
  const pollRef                         = useRef(null);

  const bothUntrained = modelsLoaded && !modelsLoaded.sensor && !modelsLoaded.vision;

  // ── Append log line (keep last 5) ─────────────────────────────────────────
  const appendLog = useCallback((line) => {
    setTrainingLog(prev => [...prev.slice(-4), `[${new Date().toLocaleTimeString()}] ${line}`]);
  }, []);

  // ── Poll /api/status for training progress ────────────────────────────────
  const startPolling = useCallback(() => {
    pollRef.current = setInterval(async () => {
      try {
        const res  = await fetch('/api/status');
        const json = await res.json();
        if (json.training_status) {
          appendLog(json.training_status);
        }
        if (json.training_complete) {
          clearInterval(pollRef.current);
          setIsTraining(false);
          if (json.results) setResults(json.results);
          appendLog('Training complete!');
        }
      } catch {
        appendLog('Error polling status…');
      }
    }, STATUS_POLL_INTERVAL);
  }, [appendLog]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // ── Train (synthetic or real) ──────────────────────────────────────────────
  const handleTrain = async (synthetic = false) => {
    setIsTraining(true);
    setError(null);
    setResults(null);
    appendLog(synthetic ? 'Generating synthetic data…' : 'Starting training…');

    try {
      const url  = synthetic ? '/api/train?synthetic=true' : '/api/train';
      const res  = await fetch(url, { method: 'POST' });
      const json = await res.json();
      appendLog(json.message ?? 'Training started on backend');
      startPolling();

      // If backend returns results immediately
      if (json.results) {
        setResults(json.results);
        setIsTraining(false);
        appendLog('Done!');
      }
    } catch (err) {
      setError(`Training failed: ${err.message}`);
      setIsTraining(false);
      appendLog(`Error: ${err.message}`);
    }
  };

  // ── Collect data ───────────────────────────────────────────────────────────
  const handleCollectToggle = async () => {
    if (isCollecting) {
      setIsCollecting(false);
      appendLog(`Stopped recording "${selectedLabel}"`);
      try {
        await fetch('/api/record/stop', { method: 'POST' });
      } catch { /* ignore */ }
    } else {
      setIsCollecting(true);
      appendLog(`Recording "${selectedLabel}" samples…`);
      try {
        await fetch(`/api/record/start?label=${selectedLabel}`, { method: 'POST' });
      } catch { /* ignore */ }
    }
  };

  // ── Styles ────────────────────────────────────────────────────────────────
  const headerStyle = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    cursor: 'pointer',
    userSelect: 'none',
    paddingBottom: expanded ? '16px' : 0,
    borderBottom: expanded ? '1px solid var(--cream-dark)' : 'none',
    transition: 'border 200ms ease',
  };

  const chevronStyle = {
    fontSize: '0.85rem',
    color: 'var(--text-light)',
    transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
    transition: 'transform 250ms ease',
    display: 'inline-block',
  };

  const sectionStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    paddingTop: '16px',
    animation: 'fadeIn 200ms ease',
  };

  const rowStyle = {
    display: 'flex',
    gap: '10px',
    alignItems: 'flex-end',
    flexWrap: 'wrap',
  };

  const logStyle = {
    background: 'var(--cream)',
    borderRadius: '10px',
    padding: '10px 14px',
    border: '1px solid var(--cream-dark)',
    maxHeight: '120px',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
  };

  const logLineStyle = {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.72rem',
    color: 'var(--text-mid)',
    animation: 'slideUp 200ms ease',
  };

  const bannerStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    background: '#FFFBEB',
    border: '1px solid #FDE68A',
    borderRadius: '10px',
    padding: '8px 14px',
    fontSize: '0.84rem',
    color: '#92400E',
  };

  const selectStyle = {
    padding: '8px 12px',
    borderRadius: '10px',
    border: '1px solid var(--cream-dark)',
    background: 'var(--cream)',
    fontFamily: 'var(--font-body)',
    fontSize: '0.85rem',
    color: 'var(--text-dark)',
    cursor: 'pointer',
    outline: 'none',
  };

  const labelFormStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  };

  return (
    <div className="card">
      {/* Collapsible header */}
      <div style={headerStyle} onClick={() => setExpanded(e => !e)} role="button" aria-expanded={expanded}>
        <p className="card-title" style={{ marginBottom: 0 }}>
          🏋️ Model Training
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {modelsLoaded && (
            <span style={{
              fontSize: '0.75rem',
              color: modelsLoaded.sensor && modelsLoaded.vision ? 'var(--green)' : '#92400E',
              fontWeight: 600,
            }}>
              {modelsLoaded.sensor && modelsLoaded.vision ? '✓ Models ready' : '⚠ Untrained'}
            </span>
          )}
          <span style={chevronStyle}>▼</span>
        </div>
      </div>

      {expanded && (
        <div style={sectionStyle}>
          {/* Untrained banner */}
          {bothUntrained && (
            <div style={bannerStyle}>
              <span>⚠️</span>
              <span>Models not trained — run training first to enable posture detection</span>
            </div>
          )}

          {error && (
            <div style={{ ...bannerStyle, background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626' }}>
              <span>❌</span><span>{error}</span>
            </div>
          )}

          {/* Quick synthetic train */}
          <div>
            <p style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-mid)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Quick Start
            </p>
            <div style={rowStyle}>
              <button
                className="btn-primary"
                onClick={() => handleTrain(true)}
                disabled={isTraining}
              >
                {isTraining ? <Spinner /> : '✨'}
                Generate Synthetic Data & Train
              </button>
            </div>
          </div>

          {/* Data collection */}
          <div>
            <p style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-mid)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Collect My Data
            </p>
            <div style={rowStyle}>
              <div style={labelFormStyle}>
                <label htmlFor="posture-label" style={{ fontSize: '0.75rem', color: 'var(--text-light)' }}>
                  Posture Label
                </label>
                <select
                  id="posture-label"
                  style={selectStyle}
                  value={selectedLabel}
                  onChange={e => setSelectedLabel(e.target.value)}
                  disabled={isCollecting}
                >
                  {LABELS.map(l => (
                    <option key={l} value={l}>{LABEL_NAMES[l]}</option>
                  ))}
                </select>
              </div>
              <button
                className={isCollecting ? 'btn-secondary' : 'btn-primary'}
                onClick={handleCollectToggle}
                style={{ alignSelf: 'flex-end', ...(isCollecting ? { borderColor: '#DC2626', color: '#DC2626' } : {}) }}
              >
                {isCollecting ? '⏹ Stop Recording' : '⏺ Start Recording'}
              </button>
              {isCollecting && (
                <span style={{ fontSize: '0.8rem', color: '#DC2626', fontWeight: 600, animation: 'blink 1s ease infinite', alignSelf: 'center' }}>
                  ● REC
                </span>
              )}
            </div>
          </div>

          {/* Train button */}
          <div>
            <p style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-mid)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Train on Collected Data
            </p>
            <button
              className="btn-primary btn-secondary"
              style={{ background: 'var(--cream-dark)', color: 'var(--text-dark)', border: '1px solid var(--cream-dark)' }}
              onClick={() => handleTrain(false)}
              disabled={isTraining}
            >
              {isTraining ? <><Spinner /> Training…</> : '🧠 Train Models'}
            </button>
          </div>

          {/* Training log */}
          {trainingLog.length > 0 && (
            <div style={logStyle}>
              <p style={{ fontSize: '0.7rem', color: 'var(--text-light)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Training Log
              </p>
              {trainingLog.map((line, i) => (
                <p key={i} style={logLineStyle}>{line}</p>
              ))}
            </div>
          )}

          {/* Results */}
          {results && (
            <div>
              <p style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-mid)', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Training Results
              </p>
              <div className="grid-2">
                {results.sensor && (
                  <ModelResultCard
                    title="Sensor Model"
                    accuracy={results.sensor.accuracy ?? 0}
                    f1={results.sensor.f1 ?? 0}
                    icon="🌡️"
                  />
                )}
                {results.vision && (
                  <ModelResultCard
                    title="Vision LSTM"
                    accuracy={results.vision.accuracy ?? 0}
                    f1={results.vision.f1 ?? 0}
                    icon="👁"
                  />
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
