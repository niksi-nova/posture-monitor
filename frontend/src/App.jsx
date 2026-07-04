import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { PostureDisplay }   from './components/PostureDisplay';
import { SensorPanel }      from './components/SensorPanel';
import { VisionPanel }      from './components/VisionPanel';
import { FusionGauge }      from './components/FusionGauge';
import { CalibrationModal } from './components/CalibrationModal';
import { TrainingPanel }    from './components/TrainingPanel';
import { SessionLog }       from './components/SessionLog';

const MAX_ALERTS = 20;

// ── Connection indicator ──────────────────────────────────────────────────────
function ConnectionBadge({ connected, latency }) {
  const dotStyle = {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    background: connected ? 'var(--green)' : '#DC2626',
    flexShrink: 0,
    boxShadow: connected ? '0 0 6px var(--green)' : '0 0 6px #DC262680',
    animation: connected ? 'pulse 2s ease infinite' : 'none',
  };
  const wrapStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '5px 12px',
    borderRadius: '100px',
    background: connected ? 'var(--green-muted)' : '#FEF2F2',
    border: `1px solid ${connected ? 'var(--green-light)' : '#FECACA'}`,
    fontSize: '0.8rem',
    fontWeight: 600,
    color: connected ? 'var(--green)' : '#DC2626',
  };
  return (
    <div style={wrapStyle}>
      <div style={dotStyle} />
      <span>{connected ? 'Live' : 'Disconnected'}</span>
      {connected && latency != null && (
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.72rem',
          color: 'var(--text-light)',
          marginLeft: '4px',
        }}>
          {latency}ms
        </span>
      )}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [status, setStatus]               = useState(null);
  const [alerts, setAlerts]               = useState([]);
  const [showCalibration, setShowCalibration] = useState(false);

  // WebSocket connection
  const { data, connected, latency, lastError } = useWebSocket('/ws');

  // ── Fetch status on mount ──────────────────────────────────────────────────
  useEffect(() => {
    fetch('/api/status')
      .then(r => r.json())
      .then(json => {
        setStatus(json);
        if (!json.calibrated) {
          setShowCalibration(true);
        }
      })
      .catch(err => {
        console.warn('Failed to fetch /api/status:', err.message);
      });
  }, []);

  // ── Accumulate alerts ──────────────────────────────────────────────────────
  useEffect(() => {
    if (data?.alert === true) {
      const newAlert = {
        timestamp:  Date.now(),
        posture:    data.posture ?? 'slouch',
        confidence: data.confidence ?? 0,
        duration:   data.alert_duration ?? 0,
      };
      setAlerts(prev => [newAlert, ...prev].slice(0, MAX_ALERTS));
    }
  }, [data]);

  // ── Calibration callbacks ──────────────────────────────────────────────────
  const handleCalibrationComplete = useCallback(() => {
    setShowCalibration(false);
    fetch('/api/status')
      .then(r => r.json())
      .then(json => setStatus(json))
      .catch(err => console.warn('Failed to fetch updated status:', err.message));
  }, []);

  const handleCalibrationSkip = useCallback(() => {
    setShowCalibration(false);
  }, []);

  // ── Styles ────────────────────────────────────────────────────────────────
  const appStyle = {
    minHeight: '100vh',
    padding: '0 0 40px 0',
  };

  const innerStyle = {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: '0 24px 24px',
  };

  // ── Header ────────────────────────────────────────────────────────────────
  const headerStyle = {
    position: 'sticky',
    top: 0,
    zIndex: 100,
    background: 'rgba(245, 240, 232, 0.92)',
    backdropFilter: 'blur(10px)',
    borderBottom: '1px solid var(--cream-dark)',
    padding: '0 24px',
    marginBottom: '24px',
  };

  const headerInnerStyle = {
    maxWidth: '1400px',
    margin: '0 auto',
    height: '64px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '16px',
  };

  const logoStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '1px',
  };

  const logoTitleStyle = {
    fontFamily: 'var(--font-display)',
    fontSize: '1.3rem',
    fontWeight: 700,
    color: 'var(--purple)',
    lineHeight: 1,
  };

  const logoSubStyle = {
    fontSize: '0.7rem',
    color: 'var(--text-light)',
    letterSpacing: '0.04em',
  };

  const headerRightStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  };

  // ── Main grid ─────────────────────────────────────────────────────────────
  const mainGridStyle = {
    display: 'grid',
    gridTemplateColumns: '380px 1fr',
    gap: '20px',
    marginBottom: '20px',
  };

  const leftColStyle = {
    display: 'flex',
    flexDirection: 'column',
  };

  const rightColStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  };

  // ── Models not trained banner ─────────────────────────────────────────────
  const showModelsBanner = status?.models_loaded?.sensor === false
    && status?.models_loaded?.vision === false;

  const modelsBannerStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    background: '#FFFBEB',
    border: '1px solid #FDE68A',
    borderRadius: '12px',
    padding: '10px 16px',
    marginBottom: '20px',
    fontSize: '0.85rem',
    color: '#92400E',
  };

  return (
    <div style={appStyle}>
      {/* ── Header ── */}
      <header style={headerStyle}>
        <div style={headerInnerStyle}>
          <div style={logoStyle}>
            <span style={logoTitleStyle}>PostureGuard</span>
            <span style={logoSubStyle}>RV College of Engineering</span>
          </div>

          <div style={headerRightStyle}>
            <ConnectionBadge connected={connected} latency={latency} />
            <button
              id="recalibrate-btn"
              className="btn-secondary btn-sm"
              onClick={() => setShowCalibration(true)}
            >
              ⟳ Recalibrate
            </button>
          </div>
        </div>
      </header>

      <div style={innerStyle}>
        {/* ── Models banner ── */}
        {showModelsBanner && (
          <div style={modelsBannerStyle}>
            <span>⚠️</span>
            <span>
              <strong>Models not trained</strong> — posture detection is inactive.
              Expand Training below to get started.
            </span>
          </div>
        )}

        {/* ── Main 2-col grid ── */}
        <div style={mainGridStyle}>
          {/* Left: hero PostureDisplay */}
          <div style={leftColStyle}>
            <PostureDisplay
              posture={data?.posture}
              confidence={data?.confidence}
              alert={data?.alert}
            />
          </div>

          {/* Right: sensor / vision / fusion stacked */}
          <div style={rightColStyle}>
            <SensorPanel sensor={data?.sensor} />
            <VisionPanel vision={data?.vision} baseline={status?.baseline_data} />
            <FusionGauge
              fusion={data?.fusion}
              posture={data?.posture}
              confidence={data?.confidence}
            />
          </div>
        </div>

        {/* ── Training panel (collapsible) ── */}
        <div style={{ marginBottom: '20px' }}>
          <TrainingPanel modelsLoaded={status?.models_loaded} />
        </div>

        {/* ── Session log ── */}
        <SessionLog alerts={alerts} />
      </div>

      {/* ── Calibration modal ── */}
      {showCalibration && (
        <CalibrationModal
          onComplete={handleCalibrationComplete}
          onSkip={handleCalibrationSkip}
        />
      )}
    </div>
  );
}
