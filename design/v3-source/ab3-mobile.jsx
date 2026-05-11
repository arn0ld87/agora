/* Mobile screens (v3 — Apple Enterprise iOS) */

const ABM = {};

// ─── Helpers ────────────────────────────────────────────────
function MStatusBar({ time = "9:41" }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "16px 28px 8px", fontSize: 16, fontWeight: 600,
      color: "#1d1d1f",
    }}>
      <span style={{ fontFamily: "var(--font-sans)" }}>{time}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <svg width="18" height="11" viewBox="0 0 18 11"><rect x="0" y="7" width="3" height="4" rx="0.5" fill="#1d1d1f"/><rect x="4.5" y="5" width="3" height="6" rx="0.5" fill="#1d1d1f"/><rect x="9" y="2.5" width="3" height="8.5" rx="0.5" fill="#1d1d1f"/><rect x="13.5" y="0" width="3" height="11" rx="0.5" fill="#1d1d1f"/></svg>
        <svg width="16" height="11" viewBox="0 0 16 11"><path d="M8 3C10 3 11.8 3.8 13 5L14 4C12.5 2.5 10.4 1.5 8 1.5C5.6 1.5 3.5 2.5 2 4L3 5C4.2 3.8 6 3 8 3Z" fill="#1d1d1f"/><circle cx="8" cy="9.5" r="1.5" fill="#1d1d1f"/></svg>
        <svg width="26" height="12" viewBox="0 0 26 12"><rect x="0.5" y="0.5" width="22" height="11" rx="3" stroke="#1d1d1f" strokeOpacity="0.4" fill="none"/><rect x="2" y="2" width="19" height="8" rx="1.5" fill="#1d1d1f"/><path d="M24 4V8C24.7 7.7 25 7 25 6C25 5.3 24.7 4.3 24 4Z" fill="#1d1d1f" fillOpacity="0.4"/></svg>
      </div>
    </div>
  );
}

function PhoneFrame({ children, theme = "light" }) {
  return (
    <div style={{
      width: 390, height: 844,
      borderRadius: 56,
      background: "#000",
      padding: 12,
      boxShadow: "0 0 0 1px rgba(0,0,0,0.15), 0 30px 80px rgba(0,0,0,0.18), 0 8px 24px rgba(0,0,0,0.10)",
      position: "relative",
    }}>
      <div style={{
        width: "100%", height: "100%",
        borderRadius: 44,
        background: theme === "light" ? "#f5f5f7" : "#000",
        overflow: "hidden",
        position: "relative",
        display: "flex", flexDirection: "column",
      }}>
        {/* Dynamic Island */}
        <div style={{
          position: "absolute", top: 11, left: "50%", transform: "translateX(-50%)",
          width: 122, height: 36, borderRadius: 18, background: "#000", zIndex: 50,
        }}/>
        {children}
        {/* Home indicator */}
        <div style={{
          position: "absolute", bottom: 8, left: "50%", transform: "translateX(-50%)",
          width: 134, height: 5, borderRadius: 3, background: "rgba(0,0,0,0.4)", zIndex: 50,
        }}/>
      </div>
    </div>
  );
}

function TabBar({ active = "runs" }) {
  const items = [
    { id: "home",     ic: "home",   l: "Overview" },
    { id: "runs",     ic: "bolt",   l: "Runs" },
    { id: "personas", ic: "users",  l: "Personas" },
    { id: "reports",  ic: "report", l: "Reports" },
    { id: "more",     ic: "more",   l: "More" },
  ];
  return (
    <div style={{
      paddingTop: 8, paddingBottom: 28,
      borderTop: "0.5px solid rgba(60,60,67,0.18)",
      background: "rgba(255,255,255,0.85)",
      backdropFilter: "saturate(180%) blur(20px)",
      WebkitBackdropFilter: "saturate(180%) blur(20px)",
      display: "flex", justifyContent: "space-around",
    }}>
      {items.map((it) => (
        <div key={it.id} style={{
          display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
          color: it.id === active ? "var(--accent)" : "#8e8e93",
          fontSize: 10, fontWeight: 500,
        }}>
          <Icon name={it.ic} size={24}/>
          <span>{it.l}</span>
        </div>
      ))}
    </div>
  );
}

// ─── 10 · Mobile · Overview ─────────────────────────────────
ABM.Overview = () => (
  <PhoneFrame>
    <MStatusBar/>
    <div style={{ flex: 1, overflow: "auto", padding: "8px 20px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0 16px" }}>
        <h1 className="t-largeTitle" style={{ margin: 0 }}>Agora</h1>
        <div style={{ width: 36, height: 36, borderRadius: 18, background: "#0066CC", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 600, fontSize: 14 }}>AL</div>
      </div>

      <div className="search" style={{ background: "rgba(118,118,128,0.12)", marginBottom: 20 }}>
        <Icon name="search" size={14}/>
        <span style={{ flex: 1, color: "#86868b" }}>Search projects, runs…</span>
      </div>

      {/* Live run card */}
      <div style={{
        borderRadius: 20, padding: 20,
        background: "linear-gradient(135deg, #0066CC, #004080)", color: "#fff",
        marginBottom: 20, boxShadow: "0 4px 16px rgba(0,102,204,0.2)",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", opacity: 0.7 }}>LIVE NOW</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600 }}>
            <span style={{ width: 6, height: 6, borderRadius: 3, background: "#34C759" }}/>Round 12 / 16
          </span>
        </div>
        <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: "-0.012em", marginTop: 12, lineHeight: 1.2 }}>EU AI Act · Public Reaction</div>
        <div style={{ fontSize: 13, opacity: 0.8, marginTop: 4 }}>214 personas · 12,840 messages</div>
        <div style={{ height: 4, borderRadius: 2, background: "rgba(255,255,255,0.25)", marginTop: 16, overflow: "hidden" }}>
          <div style={{ height: "100%", width: "74%", background: "#fff", borderRadius: 2 }}/>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button style={{ flex: 1, height: 36, borderRadius: 18, border: 0, background: "rgba(255,255,255,0.18)", color: "#fff", fontWeight: 600, fontSize: 14 }}>Pause</button>
          <button style={{ flex: 1, height: 36, borderRadius: 18, border: 0, background: "#fff", color: "#0066CC", fontWeight: 600, fontSize: 14 }}>Open run</button>
        </div>
      </div>

      <div className="t-section-head" style={{ marginBottom: 8 }}>This week</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
        {[
          { l: "Runs",       v: "48",    sub: "+12 vs prev", color: "#0066CC", ic: "bolt" },
          { l: "Personas",   v: "2,140", sub: "+340", color: "#248A3D", ic: "users" },
          { l: "Polarization", v: "0.62", sub: "−0.08", color: "#6E3CBC", ic: "graph" },
          { l: "Evidence",   v: "94%",   sub: "bound",   color: "#007A87", ic: "book" },
        ].map((m) => (
          <div key={m.l} style={{ background: "#fff", borderRadius: 14, padding: 14, boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ width: 28, height: 28, borderRadius: 8, background: m.color + "1a", color: m.color, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                <Icon name={m.ic} size={14}/>
              </span>
              <span style={{ fontSize: 11, color: "#248A3D", fontWeight: 600 }}>{m.sub}</span>
            </div>
            <div style={{ fontSize: 24, fontWeight: 600, letterSpacing: "-0.018em", marginTop: 8, fontVariantNumeric: "tabular-nums" }}>{m.v}</div>
            <div style={{ fontSize: 12, color: "#6e6e73" }}>{m.l}</div>
          </div>
        ))}
      </div>

      <div className="t-section-head" style={{ marginBottom: 8 }}>Recent runs</div>
      <div style={{ background: "#fff", borderRadius: 14, boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)", overflow: "hidden", marginBottom: 16 }}>
        {[
          { p: "Inflation · Workers", id: "RUN-0141", s: "queued",  c: "#007A87" },
          { p: "Climate Adapt Plan",  id: "RUN-0140", s: "done",    c: "#248A3D" },
          { p: "Healthcare Reform",   id: "RUN-0139", s: "failed",  c: "#C5292A" },
        ].map((r, i, arr) => (
          <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 16px", borderBottom: i < arr.length - 1 ? "0.5px solid rgba(60,60,67,0.08)" : "none" }}>
            <span style={{ width: 32, height: 32, borderRadius: 8, background: r.c + "1a", color: r.c, display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="doc" size={14}/></span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 500 }}>{r.p}</div>
              <div style={{ fontSize: 12, color: "#86868b", fontFamily: "var(--font-mono)" }}>{r.id}</div>
            </div>
            <span style={{
              fontSize: 11, fontWeight: 600, padding: "4px 10px", borderRadius: 999,
              background: r.c + "1a", color: r.c, textTransform: "capitalize",
            }}>{r.s}</span>
            <Icon name="chevron" size={14}/>
          </div>
        ))}
      </div>
    </div>
    <TabBar active="home"/>
  </PhoneFrame>
);

// ─── 11 · Mobile · Run Live ─────────────────────────────────
ABM.RunLive = () => (
  <PhoneFrame>
    <MStatusBar/>
    {/* Nav */}
    <div style={{ display: "flex", alignItems: "center", padding: "8px 16px 12px" }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--accent)", fontSize: 17, fontWeight: 400 }}>
        <Icon name="chevronD" size={18}/> Runs
      </span>
      <div style={{ flex: 1 }}/>
      <Icon name="more" size={20}/>
    </div>

    <div style={{ flex: 1, overflow: "auto", padding: "0 20px" }}>
      <div style={{ marginBottom: 8 }}>
        <span className="pill pill--blue" style={{ fontSize: 10 }}><span className="dot" style={{ background: "var(--accent)" }}></span>LIVE</span>
      </div>
      <h1 className="t-largeTitle" style={{ margin: 0, marginBottom: 4 }}>EU AI Act</h1>
      <p style={{ fontSize: 14, color: "#6e6e73", margin: 0, marginBottom: 20 }}>Round 12 of 16 · 214 personas</p>

      {/* Big progress dial */}
      <div style={{ background: "#fff", borderRadius: 20, padding: 20, marginBottom: 16, boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)", display: "flex", alignItems: "center", gap: 20 }}>
        <svg width="96" height="96" viewBox="0 0 96 96">
          <circle cx="48" cy="48" r="40" fill="none" stroke="#e5e5ea" strokeWidth="8"/>
          <circle cx="48" cy="48" r="40" fill="none" stroke="#0066CC" strokeWidth="8"
            strokeDasharray={`${0.74 * 251.3} 251.3`} strokeDashoffset={251.3 * 0.25}
            transform="rotate(-90 48 48)" strokeLinecap="round"/>
          <text x="48" y="44" textAnchor="middle" fontSize="22" fontWeight="700" fill="#1d1d1f" style={{ fontVariantNumeric: "tabular-nums" }}>74%</text>
          <text x="48" y="60" textAnchor="middle" fontSize="10" fill="#6e6e73" fontWeight="600">ROUND 12</text>
        </svg>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, color: "#6e6e73", textTransform: "uppercase", fontWeight: 600, letterSpacing: "0.04em" }}>ETA</div>
          <div style={{ fontSize: 28, fontWeight: 600, letterSpacing: "-0.018em" }}>4:18</div>
          <div style={{ fontSize: 12, color: "#6e6e73", marginTop: 4 }}>1.4M tokens · 4.2s/round avg</div>
        </div>
      </div>

      {/* Live polarization */}
      <div style={{ background: "#fff", borderRadius: 20, padding: 16, marginBottom: 16, boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Polarization</span>
          <span style={{ fontSize: 13, color: "#6E3CBC", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>0.62 ↘</span>
        </div>
        <svg viewBox="0 0 320 60" width="100%" height="60" preserveAspectRatio="none">
          <path d="M 0 50 L 30 42 L 60 38 L 90 30 L 120 26 L 150 22 L 180 26 L 210 24 L 240 18 L 270 22 L 300 16 L 320 12"
            fill="none" stroke="#6E3CBC" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M 0 50 L 30 42 L 60 38 L 90 30 L 120 26 L 150 22 L 180 26 L 210 24 L 240 18 L 270 22 L 300 16 L 320 12 L 320 60 L 0 60 Z"
            fill="#6E3CBC" opacity="0.12"/>
        </svg>
      </div>

      {/* Live messages */}
      <div className="t-section-head" style={{ marginBottom: 8 }}>Live transcript</div>
      <div style={{ background: "#fff", borderRadius: 20, padding: 4, boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)", marginBottom: 20 }}>
        {[
          { name: "Sofia K.", role: "Civic-tech", color: "#0066CC", text: "Transparency without redress is just a label.", time: "now" },
          { name: "Marcus W.", role: "SME · auto", color: "#B25000", text: "Sandbox first. Fines are not a substitute for guidance.", time: "12s" },
          { name: "Aisha O.",  role: "Civil rights", color: "#6E3CBC", text: "Article 13 needs an enforcement ladder, scaled with risk.", time: "34s" },
        ].map((m, i, arr) => (
          <div key={i} style={{ display: "flex", gap: 10, padding: 12, borderBottom: i < arr.length - 1 ? "0.5px solid rgba(60,60,67,0.08)" : "none" }}>
            <span style={{ width: 32, height: 32, borderRadius: 16, background: m.color, color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 600, flex: "none" }}>
              {m.name.split(" ").map(s => s[0]).join("")}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{m.name}</span>
                <span style={{ fontSize: 11, color: "#86868b" }}>{m.time}</span>
              </div>
              <div style={{ fontSize: 11, color: "#86868b", marginBottom: 4 }}>{m.role}</div>
              <div style={{ fontSize: 14, lineHeight: 1.4 }}>{m.text}</div>
            </div>
          </div>
        ))}
      </div>
    </div>

    {/* Floating action bar */}
    <div style={{ padding: "8px 20px 12px", display: "flex", gap: 10 }}>
      <button style={{ flex: 1, height: 50, borderRadius: 25, border: 0, background: "rgba(118,118,128,0.12)", fontSize: 16, fontWeight: 600, color: "#1d1d1f" }}>Pause</button>
      <button style={{ flex: 2, height: 50, borderRadius: 25, border: 0, background: "#0066CC", color: "#fff", fontSize: 16, fontWeight: 600 }}>Open graph</button>
    </div>
  </PhoneFrame>
);

// ─── 12 · Mobile · Persona Review (swipe) ───────────────────
ABM.PersonaReview = () => (
  <PhoneFrame>
    <MStatusBar/>
    <div style={{ display: "flex", alignItems: "center", padding: "8px 16px 12px" }}>
      <span style={{ color: "var(--accent)", fontSize: 17 }}>Cancel</span>
      <div style={{ flex: 1, textAlign: "center" }}>
        <div style={{ fontSize: 17, fontWeight: 600 }}>Review · 5 / 7</div>
        <div style={{ fontSize: 11, color: "#86868b" }}>EU AI Act</div>
      </div>
      <span style={{ color: "var(--accent)", fontSize: 17, fontWeight: 600 }}>Skip</span>
    </div>

    {/* Progress dots */}
    <div style={{ display: "flex", gap: 4, padding: "0 20px 16px" }}>
      {[true, true, true, true, false, false, false].map((on, i) => (
        <div key={i} style={{ flex: 1, height: 3, borderRadius: 1.5, background: on ? "#0066CC" : "rgba(60,60,67,0.18)" }}/>
      ))}
    </div>

    <div style={{ flex: 1, padding: "0 20px", overflow: "auto" }}>
      {/* Persona card */}
      <div style={{
        background: "#fff", borderRadius: 24, padding: 24,
        boxShadow: "0 4px 24px rgba(0,0,0,0.06), 0 0 0 0.5px rgba(60,60,67,0.12)",
        marginBottom: 16,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16 }}>
          <div style={{ width: 56, height: 56, borderRadius: 28, background: "#0066CC", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, fontWeight: 600 }}>YT</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 19, fontWeight: 600, letterSpacing: "-0.008em" }}>Yuki Tanaka</div>
            <div style={{ fontSize: 13, color: "#6e6e73" }}>Privacy researcher · Civic-tech</div>
          </div>
        </div>

        <div style={{ background: "rgba(178,80,0,0.10)", borderRadius: 12, padding: 12, marginBottom: 16, display: "flex", gap: 10 }}>
          <Icon name="sparkle" size={16} stroke={1.6}/>
          <div style={{ flex: 1, color: "#B25000", fontSize: 13 }}>
            <div style={{ fontWeight: 600, marginBottom: 2 }}>Possible duplicate · 0.71</div>
            <div>71% similarity to Sofia Klein. Consider merging or differentiating their stance.</div>
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div className="t-section-head" style={{ marginBottom: 6 }}>Stance</div>
          <div style={{ position: "relative", height: 10, background: "rgba(60,60,67,0.10)", borderRadius: 5, marginBottom: 6 }}>
            <div style={{ position: "absolute", left: "50%", top: -2, bottom: -2, width: 1, background: "rgba(60,60,67,0.25)" }}/>
            <div style={{ position: "absolute", left: "50%", top: 0, height: "100%", width: "29%", background: "#0066CC", borderRadius: "0 5px 5px 0" }}/>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#86868b" }}>
            <span>Oppose</span><span style={{ fontWeight: 600, color: "#0066CC" }}>+0.79 Strongly support</span>
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div className="t-section-head" style={{ marginBottom: 6 }}>Activity profile</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            {[["Posts/round", "3.2"], ["Reply rate", "68%"], ["Quote use", "Often"]].map(([l, v]) => (
              <div key={l} style={{ background: "#f5f5f7", borderRadius: 10, padding: 10 }}>
                <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: "-0.008em" }}>{v}</div>
                <div style={{ fontSize: 11, color: "#6e6e73" }}>{l}</div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="t-section-head" style={{ marginBottom: 6 }}>Bio</div>
          <p style={{ margin: 0, fontSize: 14, color: "#1d1d1f", lineHeight: 1.5 }}>
            Privacy researcher at a Tokyo civic-tech NGO. Focused on biometric ID systems and algorithmic redress. Reads policy drafts in original language; cites Article 13 frequently.
          </p>
        </div>
      </div>

      <div className="t-section-head" style={{ marginBottom: 8 }}>Quality heuristics</div>
      <div style={{ background: "#fff", borderRadius: 14, boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)", overflow: "hidden", marginBottom: 24 }}>
        {[
          ["Specificity", 0.78, "#248A3D"],
          ["Consistency", 0.92, "#248A3D"],
          ["Distinctiveness", 0.42, "#B25000"],
          ["Evidence-bound", 0.81, "#248A3D"],
        ].map(([l, v, c], i, arr) => (
          <div key={l} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderBottom: i < arr.length - 1 ? "0.5px solid rgba(60,60,67,0.08)" : "none" }}>
            <span style={{ flex: 1, fontSize: 14 }}>{l}</span>
            <div style={{ width: 80, height: 4, borderRadius: 2, background: "rgba(60,60,67,0.10)" }}>
              <div style={{ height: "100%", width: `${v * 100}%`, background: c, borderRadius: 2 }}/>
            </div>
            <span style={{ fontSize: 13, fontWeight: 600, color: c, minWidth: 32, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{v.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>

    <div style={{ padding: "8px 20px 12px", display: "flex", gap: 10 }}>
      <button style={{ flex: 1, height: 50, borderRadius: 25, border: 0, background: "rgba(197,41,42,0.10)", color: "#C5292A", fontSize: 16, fontWeight: 600 }}>Reject</button>
      <button style={{ flex: 1, height: 50, borderRadius: 25, border: 0, background: "rgba(0,102,204,0.10)", color: "#0066CC", fontSize: 16, fontWeight: 600 }}>Merge</button>
      <button style={{ flex: 1, height: 50, borderRadius: 25, border: 0, background: "#0066CC", color: "#fff", fontSize: 16, fontWeight: 600 }}>Approve</button>
    </div>
  </PhoneFrame>
);

// ─── 13 · Mobile · Report ───────────────────────────────────
ABM.Report = () => (
  <PhoneFrame>
    <MStatusBar/>
    <div style={{ display: "flex", alignItems: "center", padding: "8px 16px 12px" }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--accent)", fontSize: 17 }}>
        <Icon name="chevronD" size={18}/> Reports
      </span>
      <div style={{ flex: 1 }}/>
      <span style={{ color: "var(--accent)", fontSize: 17, fontWeight: 600 }}>Share</span>
    </div>

    <div style={{ flex: 1, overflow: "auto", padding: "0 20px 16px" }}>
      <div style={{ marginBottom: 4 }}>
        <span className="pill pill--green" style={{ fontSize: 10 }}><span className="dot"></span>v3 · Final</span>
      </div>
      <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.018em", margin: "8px 0 8px", lineHeight: 1.15 }}>
        EU AI Act<br/>Public Reaction
      </h1>
      <p style={{ fontSize: 13, color: "#6e6e73", margin: 0, marginBottom: 16 }}>Run #0140 · 156 personas · 16 rounds · 1 h ago</p>

      {/* Hero metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
        {[
          { l: "Messages",     v: "12,840" },
          { l: "Polarization", v: "0.62"  },
          { l: "Bridges",      v: "3" },
          { l: "Evidence",     v: "94%" },
        ].map((m) => (
          <div key={m.l} style={{ background: "#fff", borderRadius: 14, padding: 14, boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)" }}>
            <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: "-0.012em", fontVariantNumeric: "tabular-nums" }}>{m.v}</div>
            <div style={{ fontSize: 12, color: "#6e6e73" }}>{m.l}</div>
          </div>
        ))}
      </div>

      {/* Executive summary card */}
      <div style={{ background: "#fff", borderRadius: 20, padding: 20, marginBottom: 20, boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)" }}>
        <div className="t-section-head" style={{ marginBottom: 8 }}>Executive summary</div>
        <p style={{ fontSize: 17, fontWeight: 500, lineHeight: 1.4, margin: 0, letterSpacing: "-0.008em" }}>
          Civic groups and SMEs converge on transparency — but diverge sharply on enforcement.
        </p>
      </div>

      <div className="t-section-head" style={{ marginBottom: 8 }}>Key findings</div>
      <div style={{ background: "#fff", borderRadius: 20, padding: 4, marginBottom: 20, boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)" }}>
        {[
          ["Transparency obligations broadly accepted", 0.94, "#248A3D"],
          ["Enforcement is the fault-line", 0.81, "#B25000"],
          ["SMEs demand sandbox guidance", 0.88, "#248A3D"],
        ].map(([t, c, col], i, arr) => (
          <div key={t} style={{ display: "flex", gap: 12, padding: 14, borderBottom: i < arr.length - 1 ? "0.5px solid rgba(60,60,67,0.08)" : "none", alignItems: "center" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 600, color: "#0066CC", minWidth: 28 }}>0{i+1}</span>
            <span style={{ flex: 1, fontSize: 14, lineHeight: 1.35 }}>{t}</span>
            <span style={{ padding: "2px 8px", borderRadius: 8, background: col + "1a", color: col, fontSize: 11, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{c.toFixed(2)}</span>
          </div>
        ))}
      </div>

      {/* Quote */}
      <div style={{ background: "rgba(0,102,204,0.08)", borderRadius: 20, padding: 20, marginBottom: 20 }}>
        <div style={{ fontSize: 17, lineHeight: 1.4, fontWeight: 500, color: "#003a73", letterSpacing: "-0.008em", marginBottom: 12 }}>
          "Transparency without redress is just a label."
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: 14, background: "#0066CC", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 600, fontSize: 11 }}>SK</div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600 }}>Sofia Klein</div>
            <div style={{ fontSize: 11, color: "#6e6e73" }}>Civic-tech · Round 11</div>
          </div>
        </div>
      </div>
    </div>
    <TabBar active="reports"/>
  </PhoneFrame>
);

// ─── 14 · Mobile · Settings (Apple list) ────────────────────
ABM.Settings = () => {
  const Row = ({ ic, color, label, value, toggle, last }) => (
    <div style={{
      display: "flex", alignItems: "center", gap: 12, padding: "12px 16px",
      borderBottom: last ? "none" : "0.5px solid rgba(60,60,67,0.08)",
      background: "#fff",
    }}>
      <span style={{ width: 30, height: 30, borderRadius: 7, background: color, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "#fff", flex: "none" }}>
        <Icon name={ic} size={16}/>
      </span>
      <span style={{ flex: 1, fontSize: 16 }}>{label}</span>
      {value && <span style={{ fontSize: 14, color: "#86868b" }}>{value}</span>}
      {toggle !== undefined ? (
        <span className={`toggle ${toggle ? "on on--blue" : ""}`} style={{ width: 51, height: 31 }}/>
      ) : (
        <Icon name="chevron" size={14}/>
      )}
    </div>
  );

  return (
    <PhoneFrame>
      <MStatusBar/>
      <div style={{ flex: 1, overflow: "auto", padding: "8px 0 16px", background: "#f5f5f7" }}>
        <div style={{ padding: "8px 20px 16px" }}>
          <h1 className="t-largeTitle" style={{ margin: 0 }}>Settings</h1>
        </div>

        {/* Workspace card */}
        <div style={{ margin: "0 16px 16px" }}>
          <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14, padding: 16, background: "#fff" }}>
              <div style={{ width: 56, height: 56, borderRadius: 12, background: "linear-gradient(135deg,#0A84FF,#0040A0)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 22 }}>A</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: "-0.012em" }}>Acme Workspace</div>
                <div style={{ fontSize: 13, color: "#6e6e73" }}>12 members · Enterprise plan</div>
              </div>
              <Icon name="chevron" size={14}/>
            </div>
          </div>
        </div>

        <div style={{ padding: "0 32px 6px", fontSize: 13, color: "#6e6e73", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>Compute</div>
        <div style={{ margin: "0 16px 16px", borderRadius: 14, overflow: "hidden", boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)" }}>
          <Row ic="sparkle" color="#0066CC" label="Default model" value="Haiku 4.5"/>
          <Row ic="cloud"   color="#34C759" label="Cloud sync" toggle={true}/>
          <Row ic="lock"    color="#5856D6" label="Local-only mode" toggle={false} last/>
        </div>

        <div style={{ padding: "0 32px 6px", fontSize: 13, color: "#6e6e73", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>Notifications</div>
        <div style={{ margin: "0 16px 16px", borderRadius: 14, overflow: "hidden", boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)" }}>
          <Row ic="bell"  color="#FF9500" label="Run completed" toggle={true}/>
          <Row ic="bell"  color="#FF9500" label="Persona review needed" toggle={true}/>
          <Row ic="bell"  color="#FF9500" label="Polarization alert" toggle={false} last/>
        </div>

        <div style={{ padding: "0 32px 6px", fontSize: 13, color: "#6e6e73", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>About</div>
        <div style={{ margin: "0 16px 16px", borderRadius: 14, overflow: "hidden", boxShadow: "0 0 0 0.5px rgba(60,60,67,0.12)" }}>
          <Row ic="doc"      color="#8e8e93" label="Version" value="0.9.0"/>
          <Row ic="settings" color="#8e8e93" label="System status" value="All systems normal"/>
          <Row ic="book"     color="#8e8e93" label="Documentation" last/>
        </div>
      </div>
      <TabBar active="more"/>
    </PhoneFrame>
  );
};

window.ABM = ABM;
