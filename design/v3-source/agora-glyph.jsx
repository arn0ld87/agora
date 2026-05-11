/* Agora glyph — wordmark + monogram (α as graph-node) */

const AgoraGlyph = ({ size = 22, accent = "var(--accent)", ink = "var(--fg)", style = "alpha-node" }) => {
  // alpha-node: greek alpha rendered as two strokes meeting a node
  if (style === "alpha-node") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ display: "block" }}>
        {/* graph edges */}
        <path d="M3 5 L11 12 L3 19" stroke={ink} strokeWidth="1.5" strokeLinecap="square" />
        <path d="M21 5 L13 12 L21 19" stroke={ink} strokeWidth="1.5" strokeLinecap="square" />
        {/* center node */}
        <circle cx="12" cy="12" r="3" fill={accent} />
        <circle cx="12" cy="12" r="3" stroke={accent} strokeWidth="0.6" opacity="0.4" />
      </svg>
    );
  }
  // graph-cluster: three nodes connected
  if (style === "cluster") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={{ display: "block" }}>
        <line x1="6" y1="7" x2="18" y2="7" stroke={ink} strokeWidth="1.2" />
        <line x1="6" y1="7" x2="12" y2="18" stroke={ink} strokeWidth="1.2" />
        <line x1="18" y1="7" x2="12" y2="18" stroke={ink} strokeWidth="1.2" />
        <circle cx="6" cy="7" r="2.2" fill={ink} />
        <circle cx="18" cy="7" r="2.2" fill={ink} />
        <circle cx="12" cy="18" r="2.6" fill={accent} />
      </svg>
    );
  }
  // crosshair: cartographic mark
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={{ display: "block" }}>
      <circle cx="12" cy="12" r="9" stroke={ink} strokeWidth="1" />
      <line x1="12" y1="2" x2="12" y2="22" stroke={ink} strokeWidth="1" />
      <line x1="2" y1="12" x2="22" y2="12" stroke={ink} strokeWidth="1" />
      <circle cx="12" cy="12" r="2.4" fill={accent} />
    </svg>
  );
};

const AgoraLogo = ({ size = 22, accent, ink, glyphStyle = "alpha-node" }) => (
  <span className="logo">
    <AgoraGlyph size={size} accent={accent} ink={ink} style={glyphStyle} />
    <span className="wordmark">
      Agor<span className="dot">·</span>a
    </span>
  </span>
);

window.AgoraGlyph = AgoraGlyph;
window.AgoraLogo = AgoraLogo;
