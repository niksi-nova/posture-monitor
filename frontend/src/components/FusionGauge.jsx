// ── FusionGauge ───────────────────────────────────────────────────────────────
// Semicircle arc gauge showing fusion confidence + vision/sensor weight split
// + mini probability table

const GAUGE_W = 240;
const GAUGE_H = 130;
const CX = GAUGE_W / 2;
const CY = GAUGE_H - 10;  // center near bottom so arc is a proper semicircle
const R  = 100;

// Generate arc path for a semicircle (180° from left to right)
function describeArc(cx, cy, r, startAngleDeg, endAngleDeg) {
  const toRad = (d) => (d * Math.PI) / 180;
  const sx = cx + r * Math.cos(toRad(startAngleDeg));
  const sy = cy + r * Math.sin(toRad(startAngleDeg));
  const ex = cx + r * Math.cos(toRad(endAngleDeg));
  const ey = cy + r * Math.sin(toRad(endAngleDeg));
  const largeArc = Math.abs(endAngleDeg - startAngleDeg) > 180 ? 1 : 0;
  return `M ${sx} ${sy} A ${r} ${r} 0 ${largeArc} 1 ${ex} ${ey}`;
}

// Needle component
function Needle({ cx, cy, r, valueFrac }) {
  // -180° = left end, 0° = right end, mapped to 0-1 value
  const angleDeg = -180 + valueFrac * 180;
  const rad = (angleDeg * Math.PI) / 180;
  const tipX = cx + r * 0.88 * Math.cos(rad);
  const tipY = cy + r * 0.88 * Math.sin(rad);
  return (
    <g>
      <line
        x1={cx} y1={cy}
        x2={tipX} y2={tipY}
        stroke="var(--text-dark)"
        strokeWidth="2.5"
        strokeLinecap="round"
        style={{ transition: 'x2 500ms ease, y2 500ms ease' }}
      />
      <circle cx={cx} cy={cy} r="5" fill="var(--text-dark)" />
    </g>
  );
}

// Small probability mini-bar row
function ProbRow({ label, prob, color }) {
  const barW = Math.max(0, Math.min(100, Math.round((prob ?? 0) * 100)));
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      fontSize: '0.78rem',
    }}>
      <span style={{ width: '88px', color: 'var(--text-mid)', flexShrink: 0 }}>{label}</span>
      <div style={{
        flex: 1,
        height: '6px',
        background: 'var(--cream-dark)',
        borderRadius: '100px',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${barW}%`,
          height: '100%',
          background: color,
          borderRadius: '100px',
          transition: 'width 400ms ease',
        }} />
      </div>
      <span style={{
        width: '36px',
        textAlign: 'right',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.72rem',
        color: 'var(--text-light)',
      }}>
        {barW}%
      </span>
    </div>
  );
}

// Vision vs Sensor weight bar
function WeightBar({ visionWeight, sensorWeight }) {
  const vPct = Math.round((visionWeight ?? 0.5) * 100);
  const sPct = Math.round((sensorWeight ?? 0.5) * 100);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        fontSize: '0.75rem',
        color: 'var(--text-mid)',
        fontWeight: 600,
      }}>
        <span style={{ color: 'var(--purple)' }}>Vision {vPct}%</span>
        <span style={{ color: 'var(--green)' }}>Sensor {sPct}%</span>
      </div>
      <div style={{
        display: 'flex',
        height: '10px',
        borderRadius: '100px',
        overflow: 'hidden',
        border: '1px solid var(--cream-dark)',
      }}>
        <div style={{
          width: `${vPct}%`,
          background: 'var(--purple-light)',
          transition: 'width 400ms ease',
        }} />
        <div style={{
          flex: 1,
          background: 'var(--green-light)',
          transition: 'width 400ms ease',
        }} />
      </div>
    </div>
  );
}

export function FusionGauge({ fusion, posture, confidence }) {
  const conf   = confidence ?? 0;
  const isGood = posture === 'good' || conf < 0.4;
  const arcColor = isGood ? 'var(--green)' : 'var(--purple)';

  // Full background arc (grey track)
  const trackPath  = describeArc(CX, CY, R, -180, 0);
  // Filled arc proportional to confidence
  const fillAngle  = -180 + conf * 180;
  const filledPath = conf > 0 ? describeArc(CX, CY, R, -180, fillAngle) : null;

  const probs    = fusion?.probabilities  ?? {};
  const vW       = fusion?.vision_weight  ?? 0.53;
  const sW       = fusion?.sensor_weight  ?? 0.47;

  const wrapStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  };

  const gaugeWrap = {
    display: 'flex',
    justifyContent: 'center',
    position: 'relative',
  };

  const centerLabelStyle = {
    position: 'absolute',
    bottom: '18px',
    left: '50%',
    transform: 'translateX(-50%)',
    textAlign: 'center',
    pointerEvents: 'none',
  };

  const pctStyle = {
    display: 'block',
    fontFamily: 'var(--font-display)',
    fontSize: '1.8rem',
    fontWeight: 700,
    color: arcColor,
    lineHeight: 1,
    transition: 'color 300ms ease',
  };

  const subLabelStyle = {
    display: 'block',
    fontSize: '0.7rem',
    color: 'var(--text-light)',
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
    marginTop: '3px',
  };

  const dividerStyle = {
    height: '1px',
    background: 'var(--cream-dark)',
    margin: '0 -4px',
  };

  if (!fusion && confidence == null) {
    return (
      <div className="card">
        <p className="card-title">Fusion Confidence</p>
        <div className="skeleton" style={{ height: 140, borderRadius: 12 }} />
      </div>
    );
  }

  return (
    <div className="card">
      <p className="card-title">Fusion Confidence</p>

      <div style={wrapStyle}>
        {/* Semicircle gauge */}
        <div style={gaugeWrap}>
          <svg
            width={GAUGE_W}
            height={GAUGE_H}
            viewBox={`0 0 ${GAUGE_W} ${GAUGE_H}`}
            aria-label={`Fusion confidence: ${Math.round(conf * 100)}%`}
          >
            {/* Track */}
            <path
              d={trackPath}
              fill="none"
              stroke="var(--cream-dark)"
              strokeWidth="14"
              strokeLinecap="round"
            />
            {/* Filled arc */}
            {filledPath && (
              <path
                d={filledPath}
                fill="none"
                stroke={arcColor}
                strokeWidth="14"
                strokeLinecap="round"
                style={{ transition: 'stroke 300ms ease' }}
              />
            )}
            {/* Needle */}
            <Needle cx={CX} cy={CY} r={R} valueFrac={conf} />
          </svg>

          {/* Center percentage label */}
          <div style={centerLabelStyle}>
            <span style={pctStyle}>{Math.round(conf * 100)}%</span>
            <span style={subLabelStyle}>confidence</span>
          </div>
        </div>

        {/* Vision vs Sensor weight split */}
        <WeightBar visionWeight={vW} sensorWeight={sW} />

        <div style={dividerStyle} />

        {/* Probability mini-bars */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <p style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-light)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Class Probabilities
          </p>
          <ProbRow label="Good"         prob={probs.good         ?? (posture === 'good'         ? conf : 0.1)} color="var(--green)" />
          <ProbRow label="Slouch"       prob={probs.slouch       ?? (posture === 'slouch'       ? conf : 0.05)} color="var(--purple)" />
          <ProbRow label="Forward Head" prob={probs.forward_head ?? (posture === 'forward_head' ? conf : 0.05)} color="var(--purple-light)" />
        </div>
      </div>
    </div>
  );
}
