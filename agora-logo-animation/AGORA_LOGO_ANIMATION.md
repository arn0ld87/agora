# Agora Logo Animation

## Dateien

- `agora-logo-animated.svg`  
  Direkt nutzbar als animiertes SVG, zum Beispiel in `frontend/public/`.
- `agora-logo-preview.html`  
  Vorschau-Datei für Browser.

## Einbau in Agora

### 1. Datei ablegen

```bash
mkdir -p frontend/public/brand
cp agora-logo-animated.svg frontend/public/brand/agora-logo-animated.svg
```

### 2. In Vue/React/HTML einbinden

```html
<img
  src="/brand/agora-logo-animated.svg"
  alt="Agora"
  width="240"
  height="80"
/>
```

### 3. Für Splash/Loading-Screen nutzen

```html
<div class="agora-loader">
  <img src="/brand/agora-logo-animated.svg" alt="Agora wird geladen" />
</div>
```

```css
.agora-loader {
  display: grid;
  place-items: center;
  min-height: 220px;
}
```

## Animationen

- Ring zeichnet sich ein.
- Graph-Knoten springen nacheinander ein.
- Chat-Bubble erscheint.
- Wortmarke blendet sich Buchstabe für Buchstabe ein.
- `prefers-reduced-motion` wird berücksichtigt, damit Nutzer mit reduzierter Bewegung keine Daueranimation bekommen. Menschen brauchen offenbar sogar Barrierefreiheit für Logos. Fair.
