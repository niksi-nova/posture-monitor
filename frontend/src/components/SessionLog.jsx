const POSTURE_LABELS = {
  good:         { text: 'Good',         color: 'var(--green)',  bg: 'var(--green-muted)' },
  slouch:       { text: 'Slouch',       color: 'var(--purple)', bg: 'var(--purple-muted)' },
  forward_head: { text: 'Fwd. Head',    color: 'var(--purple)', bg: 'var(--purple-muted)' },
};

function formatTime(ts) {
  return new Date(ts).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });
}

function AlertEntry({ alert, isNew }) {
  const info = POSTURE_LABELS[alert.posture] ?? POSTURE_LABELS.slouch;
  const pct  = Math.round(alert.confidence * 100);

  const entryStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '12px 14px 12px 18px',
    borderRadius: '10px',
    background: '#ffffff',
    border: '1px solid var(--cream-dark)',
    borderLeft: `4px solid var(--purple)`,
    animation: isNew ? 'slideUp 300ms ease' : 'none',
    transition: 'box-shadow 200ms ease',
  };

  const timeStyle = {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.72rem',
    color: 'var(--text-light)',
    flexShrink: 0,
    minWidth: '90px',
  };

  const pillStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    background: info.bg,
    color: info.color,
    borderRadius: '100px',
    padding: '2px 10px',
    fontSize: '0.75rem',
    fontWeight: 700,
    flexShrink: 0,
  };

  const durationStyle = {
    fontSize: '0.78rem',
    color: 'var(--text-light)',
    marginLeft: 'auto',
    flexShrink: 0,
  };

  const confStyle = {
    fontSize: '0.78rem',
    color: 'var(--text-mid)',
    flexShrink: 0,
  };

  return (
    <div style={entryStyle}>
      <span style={timeStyle}>{formatTime(alert.timestamp)}</span>
      <span style={pillStyle}>{info.text}</span>
      <span style={confStyle}>{pct}% conf</span>
      <span style={durationStyle}>{alert.duration ?? 0}s</span>
    </div>
  );
}

export function SessionLog({ alerts }) {
  const isEmpty = !alerts || alerts.length === 0;

  const containerStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    maxHeight: '320px',
    overflowY: 'auto',
    padding: '2px 0',
  };

  const emptyStyle = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    padding: '32px 0',
    color: 'var(--text-light)',
  };

  const headerRowStyle = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: '12px',
  };

  const countBadgeStyle = {
    background: alerts?.length > 0 ? 'var(--purple-muted)' : 'var(--cream-dark)',
    color: alerts?.length > 0 ? 'var(--purple)' : 'var(--text-light)',
    borderRadius: '100px',
    padding: '2px 10px',
    fontSize: '0.75rem',
    fontWeight: 700,
  };

  return (
    <div className="card">
      <div style={headerRowStyle}>
        <p className="card-title" style={{ marginBottom: 0 }}>
          📋 Session Alerts
        </p>
        <span style={countBadgeStyle}>
          {isEmpty ? '0 alerts' : `${alerts.length} alert${alerts.length !== 1 ? 's' : ''}`}
        </span>
      </div>

      {isEmpty ? (
        <div style={emptyStyle}>
          <span style={{ fontSize: '2rem' }}>🎉</span>
          <p style={{ fontFamily: 'var(--font-display)', fontSize: '1rem', color: 'var(--green)' }}>
            No alerts yet — great posture!
          </p>
          <p style={{ fontSize: '0.83rem' }}>
            Alerts will appear here when poor posture is detected
          </p>
        </div>
      ) : (
        <div style={containerStyle}>
          {alerts.slice(0, 20).map((alert, i) => (
            <AlertEntry key={`${alert.timestamp}-${i}`} alert={alert} isNew={i === 0} />
          ))}
        </div>
      )}
    </div>
  );
}
