import { useMemo } from 'react';

// ── Posture SVG path definitions ────────────────────────────────────────────
// Each path is a stylized torso+head silhouette ~200×300 viewBox
// Origin is top-left; spine runs vertically through center (~x=100)

const PATHS = {
  good: {
    // Upright: straight spine, centered head, level shoulders
    body: `
      M 100 30
      C 88 30, 78 38, 75 48
      C 72 58, 73 68, 75 78
      L 68 82
      C 55 86, 48 96, 48 108
      L 48 120
      C 48 126, 52 130, 58 130
      L 70 130
      L 68 180
      C 68 188, 72 194, 78 196
      L 122 196
      C 128 194, 132 188, 132 180
      L 130 130
      L 142 130
      C 148 130, 152 126, 152 120
      L 152 108
      C 152 96, 145 86, 132 82
      L 125 78
      C 127 68, 128 58, 125 48
      C 122 38, 112 30, 100 30
      Z
    `,
    head: `
      M 100 10
      C 85 10, 74 20, 74 34
      C 74 48, 85 58, 100 58
      C 115 58, 126 48, 126 34
      C 126 20, 115 10, 100 10
      Z
    `,
    spine: `M 100 78 L 100 140`,
    spineColor: '#5A8A6A',
  },

  slouch: {
    // Hunched: curved spine, rounded shoulders forward, head angled down
    body: `
      M 100 42
      C 88 38, 76 44, 72 54
      C 68 64, 70 74, 73 82
      L 65 88
      C 50 94, 42 106, 44 118
      L 46 130
      C 47 136, 51 140, 58 139
      L 70 137
      L 72 188
      C 73 196, 78 200, 84 200
      L 124 200
      C 130 200, 134 196, 134 188
      L 134 137
      L 146 139
      C 153 140, 156 136, 156 130
      L 157 118
      C 158 106, 150 94, 136 88
      L 128 82
      C 131 74, 131 64, 127 54
      C 123 44, 112 38, 100 42
      Z
    `,
    head: `
      M 96 18
      C 81 20, 70 31, 71 45
      C 72 59, 84 68, 99 67
      C 114 66, 124 55, 123 41
      C 122 27, 111 16, 96 18
      Z
    `,
    spine: `M 100 82 C 102 100, 104 120, 106 140`,
    spineColor: '#B89FD4',
  },

  forward_head: {
    // Forward head: upright spine, head translated forward (+x), neck angled
    body: `
      M 100 30
      C 88 30, 78 38, 75 48
      C 72 58, 73 68, 75 78
      L 68 82
      C 55 86, 48 96, 48 108
      L 48 120
      C 48 126, 52 130, 58 130
      L 70 130
      L 68 180
      C 68 188, 72 194, 78 196
      L 122 196
      C 128 194, 132 188, 132 180
      L 130 130
      L 142 130
      C 148 130, 152 126, 152 120
      L 152 108
      C 152 96, 145 86, 132 82
      L 125 78
      C 127 68, 128 58, 125 48
      C 122 38, 112 30, 100 30
      Z
    `,
    head: `
      M 118 8
      C 103 8, 92 18, 92 32
      C 92 46, 103 56, 118 56
      C 133 56, 144 46, 144 32
      C 144 18, 133 8, 118 8
      Z
    `,
    spine: `M 100 78 L 100 140`,
    spineColor: '#B89FD4',
  },
};

const STATUS_LABELS = {
  good:         { text: 'Good Posture',  cls: 'status-good' },
  slouch:       { text: 'Slouching',     cls: 'status-slouch' },
  forward_head: { text: 'Forward Head',  cls: 'status-forward_head' },
};

const DEFAULT_POSTURE = 'good';

// ── Component ────────────────────────────────────────────────────────────────
export function PostureDisplay({ posture, confidence, alert }) {
  const key        = posture && PATHS[posture] ? posture : DEFAULT_POSTURE;
  const paths      = PATHS[key];
  const statusInfo = STATUS_LABELS[key];
  const pct        = confidence != null ? Math.round(confidence * 100) : null;

  const containerStyle = {
    position: 'relative',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '16px',
    padding: '28px 24px 24px',
  };

  const svgWrapperStyle = {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '50%',
    padding: '12px',
    background: 'var(--cream)',
    border: '1px solid var(--cream-dark)',
    transition: 'box-shadow 300ms ease',
    ...(alert
      ? { animation: 'pulseRing 1.4s ease infinite' }
      : {}),
  };

  const statusStyle = {
    fontFamily: 'var(--font-display)',
    fontSize: '1.5rem',
    fontWeight: 700,
    letterSpacing: '0.01em',
    transition: 'color 300ms ease',
  };

  const badgeStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    background: key === 'good' ? 'var(--green-muted)' : 'var(--purple-muted)',
    color: key === 'good' ? 'var(--green)' : 'var(--purple)',
    borderRadius: '100px',
    padding: '4px 12px',
    fontSize: '0.78rem',
    fontWeight: 600,
    fontFamily: 'var(--font-body)',
  };

  const alertBannerStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    background: '#FEF2F2',
    border: '1px solid #FECACA',
    borderRadius: '10px',
    padding: '8px 14px',
    color: '#DC2626',
    fontSize: '0.83rem',
    fontWeight: 600,
    animation: 'fadeIn 200ms ease',
  };

  const skeletonStyle = {
    width: 200,
    height: 300,
    borderRadius: 16,
  };

  if (!posture) {
    return (
      <div className="card" style={containerStyle}>
        <p className="card-title" style={{ alignSelf: 'flex-start' }}>Posture</p>
        <div className="skeleton" style={skeletonStyle} />
        <div className="skeleton" style={{ width: 120, height: 24, borderRadius: 8 }} />
      </div>
    );
  }

  return (
    <div className="card" style={containerStyle}>
      <p className="card-title" style={{ alignSelf: 'flex-start' }}>Live Posture</p>

      {/* Alert banner */}
      {alert && (
        <div style={alertBannerStyle}>
          <span>⚠️</span>
          <span>Posture Alert — please correct your position</span>
        </div>
      )}

      {/* SVG silhouette */}
      <div style={svgWrapperStyle}>
        <svg
          width="200"
          height="300"
          viewBox="0 0 200 300"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-label={`Posture visualization: ${statusInfo.text}`}
        >
          {/* Background */}
          <rect width="200" height="300" rx="16" fill="var(--cream)" />

          {/* Spine guide */}
          <path
            d={paths.spine}
            stroke={paths.spineColor}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray="4 4"
            opacity="0.5"
            style={{ transition: 'd 0.5s ease' }}
          />

          {/* Body silhouette */}
          <path
            d={paths.body}
            fill="var(--purple-light)"
            opacity="0.85"
            style={{ transition: 'd 0.5s ease' }}
          />

          {/* Head silhouette */}
          <path
            d={paths.head}
            fill="var(--purple)"
            opacity="0.9"
            style={{ transition: 'd 0.5s ease' }}
          />

          {/* Posture quality indicator dot at top */}
          <circle
            cx="170"
            cy="20"
            r="8"
            fill={key === 'good' ? 'var(--green)' : 'var(--purple)'}
            opacity="0.9"
          />
        </svg>
      </div>

      {/* Status label */}
      <div style={statusStyle} className={statusInfo.cls}>
        {statusInfo.text}
      </div>

      {/* Confidence badge */}
      {pct !== null && (
        <div style={badgeStyle}>
          <span>{pct}% confident</span>
        </div>
      )}
    </div>
  );
}
