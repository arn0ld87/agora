/**
 * Shell-Breakpoint — Single Source of Truth (Slice 7.3.2).
 *
 * Semantik: Mobile-Modus (Off-Canvas-Drawer, Hamburger-Topbar) gilt für
 * Viewport-Breiten < {@link MOBILE_BREAKPOINT_PX}. Bei exakt
 * {@link MOBILE_BREAKPOINT_PX} (768px) gilt bereits der Desktop-Modus.
 *
 * Vorher war das Verhalten an der Grenze widersprüchlich: CSS matchte
 * `max-width: 768px` (768px = mobile), während `AppShell.vue`s
 * Resize-Handler `window.innerWidth >= 768` nutzte (768px = desktop).
 * Diese Konstante vereinheitlicht die Semantik auf "Mobile = < 768".
 *
 * WICHTIG: CSS-Media-Queries sind statisch und können diesen Wert nicht
 * per Import referenzieren. Bei Änderung dieser Konstante müssen folgende
 * `@media`-Queries manuell mitgezogen werden (Kommentar verweist hierher):
 * - `AppShell.vue`: `@media (max-width: 767px)`
 * - `Topbar.vue`:   `@media (max-width: 767px)`
 */
export const MOBILE_BREAKPOINT_PX = 768

/**
 * Media-Query-String für `window.matchMedia`-Checks (z. B. `Sidebar.vue`).
 * `max-width: (MOBILE_BREAKPOINT_PX - 1)px` bildet exakt "< MOBILE_BREAKPOINT_PX" ab.
 */
export const MOBILE_MEDIA_QUERY = `(max-width: ${MOBILE_BREAKPOINT_PX - 1}px)`
