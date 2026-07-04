// ── Sensor metadata ───────────────────────────────────────────────────────────
const SENSORS = [
  { key: 'c',   label: 'Cervical',               abbr: 'C' },
  { key: 'th',  label: 'Thoracic',               abbr: 'Th' },
  { key: 'l',   label: 'Lumbar',                 abbr: 'L' },
  { key: 'tlj', label: 'Thoracolumbar Junction', abbr: 'TLJ' },
];

// ── Clamp helper ──────────────────────────────────────────────────────────────
const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

// ── BiDelta Bar ───────────────────────────────────────────────────────────────
// A centred horizontal bar. Left side = compression (negative delta).
// Right side = extension (positive delta). Range: ±0.6 mapped to 0-100%.
function BiDeltaBar({ delta }) {
  const MAX_DELTA = 0.6;
  const norm   = clamp(delta / MAX_DELTA, -1, 1);         // -1 to +1
  const leftPct  = norm < 0 ? Math.abs(norm) * 50 : 0;   // compressed
  const rightPct = norm > 0 ? norm * 50 : 0;              // extended

  const trackStyle = {
    position: 'relative',
    width: '100%',
    height: '10px',
    background: 'var(--cream-dark)',
    borderRadius: '100px',
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'center',
  };

  const leftFillStyle = {
    position: 'absolute',
    right: '50%',
    top: 0,
    bottom: 0,
    width: `${leftPct}%`,
    background: 'var(--purple-muted)',
    borderRight: `2px solid var(--purple-light)`,
    borderRadius: '100px 0 0 100px',
    transition: 'width 300ms ease',
  };

  const rightFillStyle = {
    position: 'absolute',
    left: '50%',
    top: 0,
    bottom: 0,
    width: `${rightPct}%`,
    background: 'var(--green-muted)',
    borderLeft: `2px solid var(--green-light)`,
    borderRadius: '0 100px 100px 0',
    transition: 'width 300ms ease',
  };

  const centerDotStyle = {
    position: 'absolute',
    left: '50%',
    top: '50%',
    transform: 'translate(-50%, -50%)',
    width: '4px',
    height: '14px',
    background: 'var(--text-light)',
    borderRadius: '2px',
    zIndex: 2,
  };

  return (
    <div style={trackStyle}>
      <div style={leftFillStyle} />
      <div style={rightFillStyle} />
      <div style={centerDotStyle} />
    </div>
  );
}

// ── Sensor Row ────────────────────────────────────────────────────────────────
function SensorRow({ label, delta, raw }) {
  const isPositive = delta >= 0;
  const deltaPct   = (delta * 100).toFixed(1);
  const sign       = isPositive ? '+' : '';

  const rowStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  };

  const headerStyle = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    gap: '8px',
  };

  const labelStyle = {
    fontSize: '0.8rem',
    fontWeight: 600,
    color: 'var(--text-mid)',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  };

  const deltaStyle = {
    fontSize: '0.85rem',
    fontWeight: 700,
    color: isPositive ? 'var(--green)' : 'var(--purple)',
    transition: 'color 200ms ease',
  };

  const rawStyle = {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.72rem',
    color: 'var(--text-light)',
    textAlign: 'right',
  };

  return (
    <div style={rowStyle}>
      <div style={headerStyle}>
        <span style={labelStyle}>{label}</span>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'baseline' }}>
          <span style={rawStyle}>{raw ?? '—'} ADC</span>
          <span style={deltaStyle}>{sign}{deltaPct}%</span>
        </div>
      </div>
      <BiDeltaBar delta={delta ?? 0} />
    </div>
  );
}

// ── Quality indicator ─────────────────────────────────────────────────────────
function QualityDot({ quality }) {
  const pct   = Math.round((quality ?? 0) * 100);
  const color = quality >= 0.75 ? 'var(--green)' : quality >= 0.5 ? '#D97706' : '#DC2626';

  const wrapStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginTop: '8px',
    padding: '8px 12px',
    background: 'var(--cream)',
    borderRadius: '10px',
    border: '1px solid var(--cream-dark)',
  };

  const dotStyle = {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    background: color,
    flexShrink: 0,
    boxShadow: `0 0 6px ${color}80`,
    animation: quality >= 0.5 ? 'pulse 2s ease infinite' : 'none',
  };

  return (
    <div style={wrapStyle}>
      <div style={dotStyle} />
      <span style={{ fontSize: '0.8rem', color: 'var(--text-mid)' }}>
        Signal Quality: <strong style={{ color }}>{pct}%</strong>
      </span>
    </div>
  );
}

// ── SensorPanel ───────────────────────────────────────────────────────────────
export function SensorPanel({ sensor }) {
  const panelStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '18px',
  };

  const legendStyle = {
    display: 'flex',
    gap: '14px',
    fontSize: '0.73rem',
    color: 'var(--text-light)',
    justifyContent: 'flex-end',
    marginBottom: '-6px',
  };

  const legendItemStyle = (color) => ({
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  });

  const legendDotStyle = (color) => ({
    width: '10px',
    height: '10px',
    borderRadius: '2px',
    background: color,
    flexShrink: 0,
  });

  if (!sensor) {
    return (
      <div className="card">
        <p className="card-title">Flex Sensors</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {SENSORS.map(s => (
            <div key={s.key} className="skeleton" style={{ height: 52, borderRadius: 10 }} />
          ))}
        </div>
      </div>
    );
  }

  const raw   = sensor.raw   ?? {};
  const delta = sensor.delta ?? {};

  return (
    <div className="card">
      <p className="card-title">Flex Sensors</p>

      <div style={legendStyle}>
        <div style={legendItemStyle()}>
          <div style={legendDotStyle('var(--purple-muted)')} />
          <span>Compressed</span>
        </div>
        <div style={legendItemStyle()}>
          <div style={legendDotStyle('var(--green-muted)')} />
          <span>Extended</span>
        </div>
      </div>

      <div style={panelStyle}>
        {SENSORS.map(({ key, label }) => (
          <SensorRow
            key={key}
            label={label}
            delta={delta[key] ?? 0}
            raw={raw[key]}
          />
        ))}
      </div>

      <QualityDot quality={sensor.quality} />
    </div>
  );
}
