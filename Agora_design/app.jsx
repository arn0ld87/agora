/* App entry: assembles the Design Canvas, wires Tweaks */

const { useState, useEffect, useMemo } = React;

function ApplyTweaks({ tweaks }) {
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty('--accent', tweaks.accent);
    root.style.setProperty('--neon-orange', tweaks.accent);
    root.style.setProperty('--plasma-400', tweaks.plasma);
    root.style.setProperty('--plasma-500', tweaks.plasma);
    root.style.setProperty('--r-1', tweaks.radius + 'px');
    if (tweaks.density === 'compact') {
      root.style.setProperty('--ctl-h-md', '32px');
      root.style.setProperty('--ctl-h-sm', '24px');
      root.style.setProperty('--fs-15', '14px');
    } else if (tweaks.density === 'comfy') {
      root.style.setProperty('--ctl-h-md', '40px');
      root.style.setProperty('--ctl-h-sm', '32px');
      root.style.setProperty('--fs-15', '16px');
    } else {
      root.style.setProperty('--ctl-h-md', '36px');
      root.style.setProperty('--ctl-h-sm', '28px');
      root.style.setProperty('--fs-15', '15px');
    }
    document.body.classList.toggle('hide-grid', !tweaks.showGrid);
  }, [tweaks]);
  return null;
}

function App() {
  const [tweaks, setTweak] = useTweaks(window.__AGORA_TWEAKS_DEFAULTS);

  return (
    <>
      <ApplyTweaks tweaks={tweaks} />
      <DesignCanvas
        title="Agora — Design Language"
        subtitle="UI-Kit + Workspace · v0.1 · ALPHA"
        defaultZoom={0.65}
      >
        <DCSection id="brand" title="Brand & Foundations">
          <DCArtboard id="identity" label="01 · Identity & Manifest" width={1280} height={780}>
            <ABFoundations.Identity />
          </DCArtboard>
          <DCArtboard id="palette" label="02 · Palette + Status" width={1280} height={780}>
            <ABFoundations.Color />
          </DCArtboard>
          <DCArtboard id="type" label="03 · Type-System" width={1280} height={900}>
            <ABFoundations.Type />
          </DCArtboard>
        </DCSection>

        <DCSection id="kit" title="UI-Kit · Atomare Komponenten">
          <DCArtboard id="buttons" label="04 · Buttons · Badges · Tabs" width={1280} height={1100}>
            <ABControls.Buttons />
          </DCArtboard>
          <DCArtboard id="inputs" label="05 · Inputs · Switches · Sliders" width={1280} height={1100}>
            <ABControls.Inputs />
          </DCArtboard>
          <DCArtboard id="menus" label="06 · Menus · Command-Palette · Tooltips" width={1280} height={1100}>
            <ABOverlays.MenusAndCmdK />
          </DCArtboard>
          <DCArtboard id="overlays" label="07 · Modal · Toast · Popover" width={1280} height={1100}>
            <ABOverlays.ModalAndToasts />
          </DCArtboard>
        </DCSection>

        <DCSection id="screens" title="Workspace · Screens & Pipeline">
          <DCArtboard id="shell" label="08 · Workspace-Shell · Step 03 · Live" width={1440} height={900}>
            <ABWorkspace.Shell />
          </DCArtboard>
          <DCArtboard id="personas" label="09 · Step 02 · Persona-Tabelle" width={1440} height={860}>
            <ABPipeline.Personas />
          </DCArtboard>
          <DCArtboard id="graph" label="10 · Graph & Lade-Zustände" width={1440} height={860}>
            <ABPipeline.GraphAndStates />
          </DCArtboard>
        </DCSection>
      </DesignCanvas>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Marke" />
        <TweakColor label="Akzent (Neon)" value={tweaks.accent}
          onChange={(v) => setTweak('accent', v)} />
        <TweakColor label="Plasma (2nd)" value={tweaks.plasma}
          onChange={(v) => setTweak('plasma', v)} />
        <TweakSelect label="Logo-Stil" value={tweaks.logoStyle}
          options={['alpha-node', 'alpha', 'node']}
          onChange={(v) => setTweak('logoStyle', v)} />

        <TweakSection label="System" />
        <TweakRadio label="Dichte" value={tweaks.density}
          options={['compact', 'comfortable', 'comfy']}
          onChange={(v) => setTweak('density', v)} />
        <TweakSlider label="Radius" value={tweaks.radius} min={0} max={8} step={1} unit="px"
          onChange={(v) => setTweak('radius', v)} />
        <TweakToggle label="Hintergrund-Grid" value={tweaks.showGrid}
          onChange={(v) => setTweak('showGrid', v)} />
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('app')).render(<App />);
