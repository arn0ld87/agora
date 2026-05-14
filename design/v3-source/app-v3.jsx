/* App entry — Agora Design Language v3 (Apple Enterprise · Light) */

const { useEffect } = React;

function App() {
  const [tweaks, setTweak] = useTweaks(window.__AGORA_V3_TWEAKS_DEFAULTS);

  useEffect(() => {
    const r = document.documentElement;
    r.style.setProperty("--accent", tweaks.accent);
    r.style.setProperty("--accent-hover", tweaks.accent);
  }, [tweaks]);

  return (
    <>
      <DesignCanvas
        title="Agora — Design Language v3"
        subtitle="Enterprise · Light · Desktop + Mobile · v0.9.0"
        defaultZoom={0.55}
      >
        <DCSection id="brand" title="Brand & Foundations">
          <DCArtboard id="identity" label="01 · Identity" width={1280} height={780}>
            <ABF.Identity />
          </DCArtboard>
          <DCArtboard id="color" label="02 · Color · System palette" width={1280} height={820}>
            <ABF.Color />
          </DCArtboard>
          <DCArtboard id="type" label="03 · Typography · SF / Geist" width={1280} height={1020}>
            <ABF.Type />
          </DCArtboard>
        </DCSection>

        <DCSection id="kit" title="UI Kit · Components">
          <DCArtboard id="buttons" label="04 · Buttons · Pills · Segmented" width={1280} height={920}>
            <ABC.Buttons />
          </DCArtboard>
          <DCArtboard id="inputs" label="05 · Inputs · Toggles · Lists" width={1280} height={1100}>
            <ABC.Inputs />
          </DCArtboard>
        </DCSection>

        <DCSection id="desktop" title="Workspace · Desktop">
          <DCArtboard id="hub" label="06 · Workspace Hub · Runs Dashboard" width={1440} height={900}>
            <ABS.WorkspaceHub />
          </DCArtboard>
          <DCArtboard id="review" label="07 · Persona Review · Step 03" width={1440} height={960}>
            <ABS.PersonaReview />
          </DCArtboard>
          <DCArtboard id="graph" label="08 · Knowledge Graph · Temporal" width={1440} height={900}>
            <ABS.GraphWorkspace />
          </DCArtboard>
          <DCArtboard id="report" label="09 · Report Viewer" width={1440} height={1000}>
            <ABS.Report />
          </DCArtboard>
        </DCSection>

        <DCSection id="mobile" title="Mobile · iPhone">
          <DCArtboard id="m-overview" label="10 · Overview" width={430} height={920}>
            <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-start", padding: 20 }}>
              <ABM.Overview />
            </div>
          </DCArtboard>
          <DCArtboard id="m-run" label="11 · Run · Live" width={430} height={920}>
            <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-start", padding: 20 }}>
              <ABM.RunLive />
            </div>
          </DCArtboard>
          <DCArtboard id="m-review" label="12 · Persona Review · Card" width={430} height={920}>
            <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-start", padding: 20 }}>
              <ABM.PersonaReview />
            </div>
          </DCArtboard>
          <DCArtboard id="m-report" label="13 · Report" width={430} height={920}>
            <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-start", padding: 20 }}>
              <ABM.Report />
            </div>
          </DCArtboard>
          <DCArtboard id="m-settings" label="14 · Settings" width={430} height={920}>
            <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-start", padding: 20 }}>
              <ABM.Settings />
            </div>
          </DCArtboard>
        </DCSection>
      </DesignCanvas>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Brand"/>
        <TweakColor label="Accent" value={tweaks.accent}
          options={["#0066CC", "#0A84FF", "#1C5BCE", "#2A6FDB"]}
          onChange={(v) => setTweak("accent", v)}/>
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById("app")).render(<App/>);
