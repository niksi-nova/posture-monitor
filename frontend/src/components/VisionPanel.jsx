// ── Feature definitions ───────────────────────────────────────────────────────
const FEATURES = [
  {
    key:   'fwd_head_ratio',
    label: 'Head Position',
    ref:   1.2,
    min:   0.8,
    max:   2.0,
    unit:  '',
  },
  {
    key:   'shoulder_tilt',
    label: 'Shoulder Tilt',
    ref:   0.02,
    min:   0.0,
    max:   0.15,
    unit:  '',
  },
  {
    key:   'torso_lean',
    label: 'Torso Lean',
    ref:   1.8,
    min:   1.2,
    max:   2.8,
    unit:  '',
  },
  {
    key:   'ear_sh_ratio',
    label: 'Ear-Shoulder',
    ref:   0.9,
    min:   0.5,
    max:   1.6,
    unit:  '',
  },
];

const RADIUS     = 32;
const STROKE_W   = 7;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// ── Arc Gauge ─────────────────────────────────────────────────────────────────
function ArcGauge({ label, value, refValue, min, max }) {
  const normalized = value != null
    ? Math.max(0, Math.min(1, (value - min) / (max - min)))
    : 0;

  const refNorm = Math.max(0, Math.min(1, (refValue - min) / (max - min)));

  const deviation = value != null ? Math.abs(value - refValue) / (refValue || 1) : 0;
  const isGood    = deviation < 0.10;
  const color     = isGood ? 'var(--green)' : 'var(--purple)';
  const bgColor   = isGood ? 'var(--green-muted)' : 'var(--purple-muted)';

  const dashOffset = CIRCUMFERENCE * (1 - normalized);
  // Reference tick angle in degrees: 0 = top (-90deg), going clockwise
  const refAngle   = refNorm * 360 - 90;
  const refRad     = (refAngle * Math.PI) / 180;
  const tickX      = 40 + (RADIUS - 2) * Math.cos(refRad);
  const tickY      = 40 + (RADIUS - 2) * Math.sin(refRad);
  const tickX2     = 40 + (RADIUS + 5) * Math.cos(refRad);
  const tickY2     = 40 + (RADIUS + 5) * Math.sin(refRad);

  const wrapStyle = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '6px',
  };

  const labelStyle = {
    fontSize: '0.72rem',
    fontWeight: 600,
    color: 'var(--text-mid)',
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
    lineHeight: 1.2,
  };

  const valueStyle = {
    fontSize: '0.75rem',
    color: 'var(--text-mid)',
    fontFamily: 'var(--font-mono)',
    fontWeight: 600,
  };

  const statusDotStyle = {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    background: color,
    display: 'inline-block',
    marginRight: '4px',
  };

  return (
    <div style={wrapStyle}>
      <svg width="80" height="80" viewBox="0 0 80 80">
        {/* Background circle */}
        <circle
          cx="40" cy="40" r={RADIUS}
          fill={bgColor}
          stroke="var(--cream-dark)"
          strokeWidth="1"
        />
        {/* Track ring */}
        <circle
          cx="40" cy="40" r={RADIUS}
          fill="none"
          stroke="var(--cream-dark)"
          strokeWidth={STROKE_W}
        />
        {/* Progress arc */}
        <circle
          cx="40" cy="40" r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth={STROKE_W}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={dashOffset}
          transform="rotate(-90 40 40)"
          style={{ transition: 'stroke-dashoffset 500ms ease, stroke 300ms ease' }}
        />
        {/* Reference tick */}
        {value != null && (
          <line
            x1={tickX} y1={tickY}
            x2={tickX2} y2={tickY2}
            stroke="var(--text-dark)"
            strokeWidth="2"
            strokeLinecap="round"
            opacity="0.5"
          />
        )}
        {/* Center value text */}
        <text
          x="40" y="44"
          textAnchor="middle"
          fontSize="11"
          fontFamily="'DM Sans', sans-serif"
          fontWeight="700"
          fill={color}
        >
          {value != null ? value.toFixed(2) : '—'}
        </text>
      </svg>

      <div style={{ display: 'flex', alignItems: 'center' }}>
        <span style={statusDotStyle} />
        <span style={labelStyle}>{label}</span>
      </div>
      <span style={{ ...valueStyle, color: 'var(--text-light)' }}>
        ref {refValue}
      </span>
    </div>
  );
}

// ── VisionPanel ───────────────────────────────────────────────────────────────
export function VisionPanel({ vision, baseline }) {
  const features    = vision?.features ?? null;
  const visibility  = vision?.visibility ?? null;
  const quality     = vision?.quality ?? null;
  const isAvailable = vision != null;

  const gridStyle = {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '20px',
    marginBottom: '16px',
  };

  const footerStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    marginTop: '8px',
    padding: '10px 12px',
    background: 'var(--cream)',
    borderRadius: '10px',
    border: '1px solid var(--cream-dark)',
  };

  const rowStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '0.8rem',
    color: 'var(--text-mid)',
  };

  const visibilityBarTrack = {
    flex: 1,
    height: '6px',
    background: 'var(--cream-dark)',
    borderRadius: '100px',
    overflow: 'hidden',
  };

  const visibilityBarFill = {
    height: '100%',
    width: `${Math.round((visibility ?? 0) * 100)}%`,
    background: (visibility ?? 0) > 0.7 ? 'var(--green)' : 'var(--purple)',
    borderRadius: '100px',
    transition: 'width 400ms ease',
  };

  if (!isAvailable) {
    return (
      <div className="card">
        <p className="card-title">Vision Features</p>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '10px',
          padding: '24px',
          color: 'var(--text-light)',
        }}>
          <span style={{ fontSize: '2rem' }}>📷</span>
          <p style={{ fontSize: '0.88rem', textAlign: 'center' }}>Camera Unavailable</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <p className="card-title">Vision Features</p>

      {/* Live Video Feed for Debugging/Testing */}
      <div style={{ marginBottom: '16px', borderRadius: '10px', overflow: 'hidden', border: '1px solid var(--cream-dark)', display: 'flex', justifyContent: 'center', background: '#000' }}>
        <img 
          src="/api/video_feed" 
          alt="Live Camera Feed" 
          style={{ width: '100%', maxWidth: '320px', height: 'auto', display: 'block' }} 
        />
      </div>

      {features ? (
        <div style={gridStyle}>
          {FEATURES.map((f, i) => {
            // Override with calibrated baseline if available
            const dynamicRef = baseline?.vision_reference?.[i] ?? f.ref;
            return (
              <ArcGauge
                key={f.key}
                label={f.label}
                value={features[f.key] ?? null}
                refValue={dynamicRef}
                min={f.min}
                max={f.max}
              />
            );
          })}
        </div>
      ) : (
        <div style={gridStyle}>
          {FEATURES.map(f => (
            <div key={f.key} className="skeleton" style={{ height: 100, borderRadius: 12 }} />
          ))}
        </div>
      )}

      {baseline?.calibrated_at && (
        <div style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-light)', marginTop: '8px' }}>
          Last calibrated: {new Date(baseline.calibrated_at).toLocaleTimeString()}
        </div>
      )}

      {/* Footer */}
      <div style={footerStyle}>
        {/* Visibility */}
        <div style={rowStyle}>
          <span>👁</span>
          <span>Camera Visibility</span>
          <div style={visibilityBarTrack}>
            <div style={visibilityBarFill} />
          </div>
          <span style={{ fontWeight: 700, minWidth: '32px', textAlign: 'right' }}>
            {visibility != null ? `${Math.round(visibility * 100)}%` : '—'}
          </span>
        </div>
        {/* Quality */}
        {quality != null && (
          <div style={rowStyle}>
            <span>✦</span>
            <span>Detection Quality</span>
            <div style={{ ...visibilityBarTrack }}>
              <div style={{ ...visibilityBarFill, width: `${Math.round(quality * 100)}%` }} />
            </div>
            <span style={{ fontWeight: 700, minWidth: '32px', textAlign: 'right' }}>
              {Math.round(quality * 100)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
