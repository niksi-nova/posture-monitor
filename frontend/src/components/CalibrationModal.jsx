import { useState, useEffect, useRef } from 'react';

const TOTAL_SECONDS = 10;
const CIRCUMFERENCE = 2 * Math.PI * 44; // r=44

export function CalibrationModal({ onComplete, onSkip }) {
  const [phase, setPhase]       = useState('idle');  // idle | calibrating | done
  const [remaining, setRemaining] = useState(TOTAL_SECONDS);
  const [error, setError]       = useState(null);
  const intervalRef             = useRef(null);

  // ── Start calibration ────────────────────────────────────────────────────
  const handleBegin = async () => {
    setError(null);
    setPhase('calibrating');
    setRemaining(TOTAL_SECONDS);

    // POST to backend
    try {
      await fetch('/api/calibrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
    } catch (err) {
      // Non-fatal: calibrate locally even if backend call fails
      console.warn('Calibration API call failed:', err.message);
    }

    // Countdown
    intervalRef.current = setInterval(() => {
      setRemaining(prev => {
        if (prev <= 1) {
          clearInterval(intervalRef.current);
          setPhase('done');
          setTimeout(onComplete, 800);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // ── SVG ring progress ────────────────────────────────────────────────────
  const progress   = (TOTAL_SECONDS - remaining) / TOTAL_SECONDS;  // 0→1
  const dashOffset = CIRCUMFERENCE * (1 - progress);
  const ringColor  = phase === 'done' ? 'var(--green)' : 'var(--purple)';

  // ── Styles ────────────────────────────────────────────────────────────────
  const overlayStyle = {
    position: 'fixed',
    inset: 0,
    background: 'rgba(245, 240, 232, 0.88)',
    backdropFilter: 'blur(8px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    animation: 'fadeIn 200ms ease',
  };

  const modalStyle = {
    background: '#ffffff',
    borderRadius: '24px',
    boxShadow: '0 8px 40px rgba(0,0,0,0.12)',
    border: '1px solid var(--cream-dark)',
    padding: '40px 48px',
    width: 'min(520px, 90vw)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '24px',
    position: 'relative',
    animation: 'slideUp 300ms ease',
  };

  const closeStyle = {
    position: 'absolute',
    top: '16px',
    right: '16px',
    background: 'var(--cream)',
    border: '1px solid var(--cream-dark)',
    borderRadius: '50%',
    width: '32px',
    height: '32px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '1rem',
    color: 'var(--text-mid)',
    transition: 'background var(--transition-fast)',
    fontFamily: 'var(--font-body)',
  };

  const titleStyle = {
    fontFamily: 'var(--font-display)',
    fontSize: '1.7rem',
    fontWeight: 700,
    color: 'var(--text-dark)',
    textAlign: 'center',
  };

  const instrStyle = {
    fontSize: '0.92rem',
    color: 'var(--text-mid)',
    textAlign: 'center',
    lineHeight: 1.7,
    maxWidth: '340px',
  };

  const ringWrap = {
    position: 'relative',
    width: '100px',
    height: '100px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  };

  const countdownStyle = {
    position: 'absolute',
    fontFamily: 'var(--font-display)',
    fontSize: '2.2rem',
    fontWeight: 700,
    color: ringColor,
    transition: 'color 300ms ease',
    userSelect: 'none',
  };

  const tipsStyle = {
    background: 'var(--cream)',
    borderRadius: '12px',
    padding: '16px 20px',
    width: '100%',
    border: '1px solid var(--cream-dark)',
  };

  const tipsList = {
    listStyle: 'none',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  };

  const tipItemStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '0.83rem',
    color: 'var(--text-mid)',
  };

  const btnRowStyle = {
    display: 'flex',
    gap: '12px',
    width: '100%',
  };

  return (
    <div style={overlayStyle} role="dialog" aria-modal="true" aria-labelledby="cal-title">
      <div style={modalStyle}>
        {/* Close button */}
        <button style={closeStyle} onClick={onSkip} aria-label="Skip calibration">✕</button>

        {/* Title */}
        <h2 id="cal-title" style={titleStyle}>
          {phase === 'done' ? '✓ Calibrated!' : 'Calibration'}
        </h2>

        {/* Instructions */}
        <p style={instrStyle}>
          {phase === 'idle'
            ? 'Sit upright and look straight ahead. Hold this position for 10 seconds while we capture your ideal posture baseline.'
            : phase === 'calibrating'
            ? 'Hold still — capturing your baseline posture...'
            : 'Calibration complete! Your baseline has been saved.'
          }
        </p>

        {/* Countdown ring */}
        <div style={ringWrap}>
          <svg width="100" height="100" viewBox="0 0 100 100">
            {/* Background track */}
            <circle
              cx="50" cy="50" r="44"
              fill="none"
              stroke="var(--cream-dark)"
              strokeWidth="8"
            />
            {/* Progress ring */}
            <circle
              cx="50" cy="50" r="44"
              fill="none"
              stroke={ringColor}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={CIRCUMFERENCE}
              strokeDashoffset={dashOffset}
              transform="rotate(-90 50 50)"
              style={{ transition: 'stroke-dashoffset 1s linear, stroke 300ms ease' }}
            />
          </svg>
          <span style={countdownStyle}>
            {phase === 'done' ? '✓' : remaining}
          </span>
        </div>

        {/* Tips (shown in idle) */}
        {phase === 'idle' && (
          <div style={tipsStyle}>
            <p style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-mid)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '10px' }}>
              Tips for best results
            </p>
            <ul style={tipsList}>
              {[
                '🪑  Sit with both feet flat on the floor',
                '👀  Eyes level with your screen',
                '💆  Relax your shoulders — don\'t force it',
                '📷  Make sure your face is visible to the camera',
              ].map((tip, i) => (
                <li key={i} style={tipItemStyle}>{tip}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Error */}
        {error && (
          <p style={{ color: '#DC2626', fontSize: '0.85rem', textAlign: 'center' }}>{error}</p>
        )}

        {/* Action buttons */}
        {phase === 'idle' && (
          <div style={btnRowStyle}>
            <button className="btn-secondary" style={{ flex: 1 }} onClick={onSkip}>
              Skip for now
            </button>
            <button className="btn-primary" style={{ flex: 2 }} onClick={handleBegin}>
              Begin Calibration
            </button>
          </div>
        )}

        {phase === 'calibrating' && (
          <button
            className="btn-secondary"
            style={{ width: '100%' }}
            disabled
          >
            Calibrating…
          </button>
        )}
      </div>
    </div>
  );
}
