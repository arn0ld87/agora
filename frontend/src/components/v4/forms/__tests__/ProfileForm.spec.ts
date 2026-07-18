/**
 * ProfileForm — Vitest-Smokes (Onboarding Slice 2).
 *
 * Tests:
 *  1. Mountet ohne Crash, Felder aus `profile`-Prop vorbefüllt.
 *  2. i18n-Keys lösen auf (kein "profileSettings.*"-Rohdot im DOM).
 *  3. Pflichtfeld display_name: leer → Fehlermeldung + save-Button disabled.
 *  4. save() emittiert korrektes Payload bei validem Formular.
 *  5. Avatar-Größenvorprüfung: zu große Datei → Fehlermeldung, kein Emit.
 *  6. Avatar-Typvorprüfung: falscher MIME-Type → Fehlermeldung, kein Emit.
 *  7. Gültige Avatar-Datei → emittiert 'upload-avatar'.
 *  8. delete-avatar-Button emittiert 'delete-avatar'.
 *  9. Verstecktes Avatar-Dateifeld hat einen lokalisierten Accessible Name.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ProfileForm from '../ProfileForm.vue'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import type { UserProfile } from '@/contracts/userProfileContract'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })
}

function makeProfile(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    avatar_ref: null,
    display_name: 'Alex Schneider',
    username: 'alex',
    role: 'Maintainer',
    organisation: 'Agora',
    language: 'de',
    timezone: 'Europe/Berlin',
    report_language: 'de',
    theme: 'system',
    privacy_mode: 'standard',
    created_at: '2026-07-11T00:00:00Z',
    updated_at: '2026-07-11T00:00:00Z',
    ...overrides,
  }
}

interface MountFormProps {
  profile?: UserProfile | null
  avatarUrl?: string | null
  saving?: boolean
}

function mountForm(props: MountFormProps = {}) {
  return mount(ProfileForm, {
    props: { profile: makeProfile(), avatarUrl: null, saving: false, ...props },
    global: { plugins: [makeI18n()] },
  })
}

describe('ProfileForm', () => {
  it('Test 1: mountet ohne Crash, Felder aus profile-Prop vorbefüllt', () => {
    const w = mountForm()
    expect(w.exists()).toBe(true)
    const displayNameInput = w.get('[data-testid="profile-form-display-name"]').element as HTMLInputElement
    expect(displayNameInput.value).toBe('Alex Schneider')
  })

  it('Test 2: i18n-Keys lösen auf (kein Rohdot im DOM)', () => {
    const w = mountForm()
    expect(w.text()).not.toMatch(/profileSettings\./)
  })

  it('Test 3: leerer display_name → Fehlermeldung + Save-Button disabled', async () => {
    const w = mountForm({ profile: makeProfile({ display_name: '' }) })
    // Save-Button ist der letzte Button im Formular; über disabled-Attribut prüfen.
    const primaryBtn = w.findAll('button').at(-1)
    expect(primaryBtn?.attributes('disabled')).toBeDefined()

    await w.get('[data-testid="profile-form-display-name"]').trigger('blur')
    expect(w.text()).toContain(de.profileSettings.form.displayNameRequired)
  })

  it('Test 4: save() emittiert korrektes Payload bei validem Formular', async () => {
    const w = mountForm()
    const primaryBtn = w.findAll('button').at(-1)
    await primaryBtn?.trigger('click')

    const saveEvents = w.emitted('save')
    expect(saveEvents).toBeTruthy()
    expect(saveEvents?.[0]?.[0]).toMatchObject({
      display_name: 'Alex Schneider',
      username: 'alex',
      role: 'Maintainer',
      organisation: 'Agora',
      language: 'de',
      timezone: 'Europe/Berlin',
      report_language: 'de',
      theme: 'system',
      privacy_mode: 'standard',
    })
  })

  it('Test 5: Avatar-Größenvorprüfung — zu große Datei löst Fehler aus, kein Emit', async () => {
    const w = mountForm()
    const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'big.png', { type: 'image/png' })
    const input = w.get('[data-testid="avatar-file-input"]')
    Object.defineProperty(input.element, 'files', { value: [big], configurable: true })
    await input.trigger('change')

    expect(w.text()).toContain(de.profileSettings.form.avatarTooLarge)
    expect(w.emitted('upload-avatar')).toBeFalsy()
  })

  it('Test 6: Avatar-Typvorprüfung — falscher MIME-Type löst Fehler aus, kein Emit', async () => {
    const w = mountForm()
    const svg = new File(['<svg/>'], 'evil.svg', { type: 'image/svg+xml' })
    const input = w.get('[data-testid="avatar-file-input"]')
    Object.defineProperty(input.element, 'files', { value: [svg], configurable: true })
    await input.trigger('change')

    expect(w.text()).toContain(de.profileSettings.form.avatarUnsupportedType)
    expect(w.emitted('upload-avatar')).toBeFalsy()
  })

  it('Test 7: gültige Avatar-Datei emittiert upload-avatar', async () => {
    const w = mountForm()
    const png = new File([new Uint8Array(1024)], 'ok.png', { type: 'image/png' })
    const input = w.get('[data-testid="avatar-file-input"]')
    Object.defineProperty(input.element, 'files', { value: [png], configurable: true })
    await input.trigger('change')

    const events = w.emitted('upload-avatar')
    expect(events).toBeTruthy()
    expect(events?.[0]?.[0]).toBe(png)
  })

  it('Test 8: delete-avatar-Button emittiert delete-avatar', async () => {
    const w = mountForm({ avatarUrl: 'http://localhost/api/profile/avatar?v=x' })
    const deleteBtn = w.findAll('button').find((b) =>
      b.text() === de.profileSettings.form.avatarDeleteBtn,
    )
    expect(deleteBtn).toBeTruthy()
    await deleteBtn?.trigger('click')
    expect(w.emitted('delete-avatar')).toBeTruthy()
  })

  it('Test 9: Avatar-Dateifeld hat lokalisierten Accessible Name', () => {
    const w = mountForm()
    const input = w.get('[data-testid="avatar-file-input"]')
    expect(input.attributes('aria-label')).toBe(de.profileSettings.form.avatarUploadBtn)
  })
})
