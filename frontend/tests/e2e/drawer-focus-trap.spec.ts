/**
 * Slice 7.3.2 — Focus-Trap für den mobilen Drawer.
 *
 * Prüft:
 * - Öffnen via Hamburger setzt Fokus in den Drawer.
 * - Tab am letzten fokussierbaren Element im Drawer springt zyklisch zum ersten
 *   (FocusScope aus reka-ui, loop+trapped reaktiv an mobileNavOpen gebunden).
 * - Shift+Tab am ersten Element springt zyklisch zum letzten.
 * - Main/Topbar sind während geöffnetem Drawer `inert` (nicht fokussierbar).
 * - Escape schließt den Drawer und der Fokus kehrt zum Hamburger-Trigger zurück.
 *
 * Stack: Playwright (siehe global-setup.ts + scripts/e2e-up.sh für den Full-Stack-Lifecycle).
 * Auth: Single-User-Token-Mode via localStorage (siehe helpers/auth.ts).
 */
import { test, expect } from '@playwright/test';
import { injectAuthToken } from './helpers/auth';

const MOBILE_VIEWPORT = { width: 375, height: 800 };
const DRAWER_SELECTOR = '[data-app-shell-drawer]';
const HAMBURGER_SELECTOR = '.topbar__hamburger';

test.describe('Slice 7.3.2 · Mobiler Drawer — Focus-Trap', () => {
  test.beforeEach(async ({ context, page }) => {
    await injectAuthToken(context);
    await page.setViewportSize(MOBILE_VIEWPORT);
  });

  test('Hamburger öffnet Drawer und setzt initialen Fokus hinein', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    const hamburger = page.locator(HAMBURGER_SELECTOR);
    await hamburger.click();

    const drawer = page.locator(DRAWER_SELECTOR);
    await expect(drawer).toHaveAttribute('role', 'dialog');
    await expect(drawer).toHaveAttribute('aria-modal', 'true');

    const focusInsideDrawer = await drawer.evaluate(
      (el, sel) => el.contains(document.querySelector(sel)),
      HAMBURGER_SELECTOR,
    );
    // Fokus liegt NICHT mehr auf dem Hamburger, sondern im Drawer.
    expect(focusInsideDrawer).toBe(false);
    const activeInsideDrawer = await drawer.evaluate((el) => el.contains(document.activeElement));
    expect(activeInsideDrawer).toBe(true);
  });

  test('Tab am letzten Element im Drawer springt zyklisch zum ersten', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    await page.locator(HAMBURGER_SELECTOR).click();

    const drawer = page.locator(DRAWER_SELECTOR);
    await expect(drawer).toBeVisible();

    const focusableCount = await drawer
      .locator(
        'button:not([disabled]), [href]:not([aria-disabled="true"]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      .count();
    expect(focusableCount).toBeGreaterThan(1);

    // Focus auf das letzte fokussierbare Element im Drawer setzen (Footer-Collapse-Button).
    await drawer.locator('.sidebar__footer').focus();
    await page.keyboard.press('Tab');

    const focusIsFirst = await drawer.evaluate((el) => {
      const candidates = el.querySelectorAll(
        'button:not([disabled]), [href]:not([aria-disabled="true"]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      return candidates[0] === document.activeElement;
    });
    expect(focusIsFirst).toBe(true);
  });

  test('Shift+Tab am ersten Element im Drawer springt zyklisch zum letzten', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    await page.locator(HAMBURGER_SELECTOR).click();

    const drawer = page.locator(DRAWER_SELECTOR);
    await expect(drawer).toBeVisible();

    const first = drawer.locator(
      'button:not([disabled]), [href]:not([aria-disabled="true"]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ).first();
    await first.focus();
    await page.keyboard.press('Shift+Tab');

    const focusIsLast = await drawer.evaluate((el) => {
      const candidates = el.querySelectorAll(
        'button:not([disabled]), [href]:not([aria-disabled="true"]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      return candidates[candidates.length - 1] === document.activeElement;
    });
    expect(focusIsLast).toBe(true);
  });

  test('Main und Topbar sind waehrend geoeffnetem Drawer inert (nicht fokussierbar)', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    await page.locator(HAMBURGER_SELECTOR).click();
    await expect(page.locator(DRAWER_SELECTOR)).toBeVisible();

    await expect(page.locator('.app-shell__main')).toHaveJSProperty('inert', true);
    await expect(page.locator('.app-shell__topbar')).toHaveJSProperty('inert', true);
  });

  test('Escape schliesst den Drawer und Fokus kehrt zum Hamburger zurueck', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    const hamburger = page.locator(HAMBURGER_SELECTOR);
    await hamburger.click();
    await expect(page.locator(DRAWER_SELECTOR)).toBeVisible();

    await page.keyboard.press('Escape');

    await expect(page.locator(DRAWER_SELECTOR)).not.toBeVisible();
    const hamburgerFocused = await hamburger.evaluate((el) => el === document.activeElement);
    expect(hamburgerFocused).toBe(true);
  });
});
