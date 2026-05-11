/* Agora Design System — App Shell (Sidebar + Header) */

const DS = {};

const DS_NAV = [
  { id: "dashboard",  icon: "home",   label: "Dashboard" },
  { id: "runs",       icon: "branch", label: "Runs" },
  { id: "projects",   icon: "folder", label: "Projects" },
  { id: "datasets",   icon: "layers", label: "Datasets" },
  { id: "templates",  icon: "doc",    label: "Templates" },
  { id: "monitoring", icon: "spark",  label: "Monitoring" },
];

const DS_SETTINGS = [
  { id: "general",      label: "General" },
  { id: "integrations", label: "Integrations" },
  { id: "users-teams",  label: "Users & Teams" },
  { id: "api-keys",     label: "API Keys" },
  { id: "llm-routing",  label: "LLM Routing" },
  { id: "audit-logs",   label: "Audit Logs" },
];

// Brand mark — Agora "A" triangle glyph
function DSGlyph({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <defs>
        <linearGradient id="dsglyph" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0" stopColor="#0A84FF"/>
          <stop offset="1" stopColor="#0040A0"/>
        </linearGradient>
      </defs>
      <path d="M16 4 L28 27 L4 27 Z" stroke="url(#dsglyph)" strokeWidth="2.4" strokeLinejoin="round" fill="none"/>
      <path d="M11 21 L21 21" stroke="url(#dsglyph)" strokeWidth="2.4" strokeLinecap="round"/>
    </svg>
  );
}

function DSSidebar({ active, openGroup, subActive }) {
  const settingsOpen = openGroup === "settings";
  return (
    <aside style={{
      width: 220, background: "#fff", borderRight: "1px solid var(--hairline)",
      display: "flex", flexDirection: "column",
    }}>
      <div style={{ height: 64, display: "flex", alignItems: "center", gap: 10, padding: "0 18px" }}>
        <DSGlyph size={26}/>
        <span style={{ fontSize: 19, fontWeight: 600, letterSpacing: "-0.02em" }}>Agora</span>
      </div>

      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 2, flex: 1 }}>
        {DS_NAV.map((n) => {
          const isActive = active === n.id && !settingsOpen;
          return (
            <div key={n.id} style={{
              display: "flex", alignItems: "center", gap: 10,
              height: 36, padding: "0 10px", borderRadius: 8,
              background: isActive ? "var(--accent-tint-bg)" : "transparent",
              color: isActive ? "var(--accent)" : "var(--text-primary)",
              fontSize: 14, fontWeight: isActive ? 600 : 500,
            }}>
              <Icon name={n.icon} size={18} stroke={1.6}/>
              <span>{n.label}</span>
            </div>
          );
        })}

        {/* Settings group */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          height: 36, padding: "0 10px", borderRadius: 8, marginTop: 12,
          background: settingsOpen ? "transparent" : (active === "settings" ? "var(--accent-tint-bg)" : "transparent"),
          color: "var(--text-primary)", fontSize: 14, fontWeight: 500,
        }}>
          <Icon name="settings" size={18} stroke={1.6}/>
          <span style={{ flex: 1 }}>Settings</span>
          <Icon name={settingsOpen ? "chevronD" : "chevron"} size={12}/>
        </div>

        {settingsOpen && (
          <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 2 }}>
            {DS_SETTINGS.map((s) => {
              const isActive = subActive === s.id;
              return (
                <div key={s.id} style={{
                  display: "flex", alignItems: "center",
                  height: 32, padding: "0 10px 0 38px", borderRadius: 8,
                  background: isActive ? "var(--accent-tint-bg)" : "transparent",
                  color: isActive ? "var(--accent)" : "var(--text-primary)",
                  fontSize: 13.5, fontWeight: isActive ? 600 : 500,
                  borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                  marginLeft: 0,
                }}>
                  {s.label}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ padding: "10px 18px", borderTop: "1px solid var(--separator)",
        display: "flex", alignItems: "center", gap: 10,
        color: "var(--text-secondary)", fontSize: 13, fontWeight: 500,
      }}>
        <Icon name="arrowL" size={14}/>
        <span>Collapse</span>
      </div>
    </aside>
  );
}

function DSHeader({ crumbs = [], badge = 3 }) {
  return (
    <header style={{
      height: 64, padding: "0 24px", background: "#fff",
      borderBottom: "1px solid var(--hairline)",
      display: "flex", alignItems: "center", gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, fontSize: 14, color: "var(--text-secondary)" }}>
        {crumbs.map((c, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span style={{ color: "var(--text-quaternary)" }}>/</span>}
            <span style={{ color: i === crumbs.length - 1 ? "var(--text-primary)" : "var(--text-secondary)",
              fontWeight: i === crumbs.length - 1 ? 600 : 500 }}>{c}</span>
          </React.Fragment>
        ))}
      </div>

      <button style={{
        width: 36, height: 36, borderRadius: 8, background: "transparent",
        border: 0, color: "var(--text-secondary)", display: "inline-flex",
        alignItems: "center", justifyContent: "center", cursor: "pointer",
      }}>
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="3.5" stroke="currentColor" strokeWidth="1.6"/>
          {[0,45,90,135,180,225,270,315].map((a) => {
            const r1 = 5.6, r2 = 7.2;
            const rad = a * Math.PI / 180;
            return <line key={a} x1={10 + r1*Math.cos(rad)} y1={10 + r1*Math.sin(rad)}
              x2={10 + r2*Math.cos(rad)} y2={10 + r2*Math.sin(rad)}
              stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>;
          })}
        </svg>
      </button>

      <button style={{
        width: 36, height: 36, borderRadius: 8, background: "transparent",
        border: 0, color: "var(--text-secondary)", display: "inline-flex",
        alignItems: "center", justifyContent: "center", cursor: "pointer",
      }}>
        <Icon name="book" size={18}/>
      </button>

      <div style={{ position: "relative" }}>
        <button style={{
          width: 36, height: 36, borderRadius: 8, background: "transparent",
          border: 0, color: "var(--text-secondary)", display: "inline-flex",
          alignItems: "center", justifyContent: "center", cursor: "pointer",
        }}>
          <Icon name="bell" size={18}/>
        </button>
        {badge > 0 && (
          <span style={{
            position: "absolute", top: 4, right: 4, minWidth: 16, height: 16,
            borderRadius: 8, background: "var(--accent)", color: "#fff",
            fontSize: 10, fontWeight: 700, display: "flex",
            alignItems: "center", justifyContent: "center", padding: "0 4px",
            boxShadow: "0 0 0 2px #fff",
          }}>{badge}</span>
        )}
      </div>

      <div style={{
        display: "flex", alignItems: "center", gap: 10, padding: "4px 10px 4px 4px",
        borderRadius: 999, marginLeft: 8,
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          background: "var(--accent-tint-bg)", color: "var(--accent)",
          fontSize: 12, fontWeight: 700, display: "flex",
          alignItems: "center", justifyContent: "center",
        }}>AD</div>
        <span style={{ fontSize: 14, fontWeight: 600 }}>Alex Developer</span>
        <Icon name="chevronD" size={12}/>
      </div>
    </header>
  );
}

function DSAppShell({ active, openGroup = "", subActive = "", crumbs = [], children }) {
  return (
    <div style={{
      width: "100%", height: "100%",
      display: "grid", gridTemplateColumns: "220px 1fr", gridTemplateRows: "64px 1fr",
      background: "var(--surface-canvas)",
    }}>
      <div style={{ gridRow: "1 / 3", gridColumn: 1 }}>
        <DSSidebar active={active} openGroup={openGroup} subActive={subActive}/>
      </div>
      <div style={{ gridRow: 1, gridColumn: 2 }}>
        <DSHeader crumbs={crumbs}/>
      </div>
      <div style={{ gridRow: 2, gridColumn: 2, overflow: "hidden", padding: "28px 36px" }}>
        {children}
      </div>
    </div>
  );
}

function DSPageHeader({ title, subtitle, right }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 22 }}>
      <div style={{ flex: 1 }}>
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, letterSpacing: "-0.018em", color: "var(--text-primary)" }}>{title}</h1>
        {subtitle && <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: 14 }}>{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

function DSCard({ title, subtitle, right, pad = 22, children, style }) {
  return (
    <div style={{
      background: "#fff", borderRadius: 14,
      boxShadow: "0 0 0 1px var(--hairline), 0 1px 1px rgba(0,0,0,0.02)",
      padding: pad, ...style,
    }}>
      {(title || right) && (
        <div style={{ display: "flex", alignItems: "flex-start", marginBottom: subtitle ? 14 : 16, gap: 12 }}>
          <div style={{ flex: 1 }}>
            {title && <h2 style={{ margin: 0, fontSize: 17, fontWeight: 600, letterSpacing: "-0.005em" }}>{title}</h2>}
            {subtitle && <div style={{ marginTop: 4, color: "var(--text-secondary)", fontSize: 13 }}>{subtitle}</div>}
          </div>
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

// Field with label above
function DSField({ label, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ fontSize: 12.5, fontWeight: 500, color: "var(--text-secondary)" }}>{label}</label>
      {children}
    </div>
  );
}

function DSSelect({ value, placeholder }) {
  return (
    <div style={{
      height: 36, padding: "0 12px",
      borderRadius: 8, background: "#fff",
      border: "1px solid var(--hairline)",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      fontSize: 14, color: value ? "var(--text-primary)" : "var(--text-tertiary)",
    }}>
      <span>{value || placeholder}</span>
      <Icon name="chevronD" size={12}/>
    </div>
  );
}

function DSInput({ value, placeholder, mono }) {
  return (
    <div style={{
      height: 36, padding: "0 12px",
      borderRadius: 8, background: "#fff",
      border: "1px solid var(--hairline)",
      display: "flex", alignItems: "center",
      fontSize: 14, color: value ? "var(--text-primary)" : "var(--text-tertiary)",
      fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
    }}>
      <span>{value || placeholder}</span>
    </div>
  );
}

window.DS = DS;
window.DSAppShell = DSAppShell;
window.DSPageHeader = DSPageHeader;
window.DSCard = DSCard;
window.DSField = DSField;
window.DSSelect = DSSelect;
window.DSInput = DSInput;
window.DSGlyph = DSGlyph;
