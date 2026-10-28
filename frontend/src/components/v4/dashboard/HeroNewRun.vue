<script setup lang="ts">
/**
 * HeroNewRun — primärer Aktions-Block des Dashboards.
 *
 * Workbench-These: ruhige Card, drei Zonen (Quelle | Modell+Sprache | Aktion),
 * Akzent-Aktion rechts. Keine Glows, keine Marketing-Kicker.
 *
 * Spiegelt den bestehenden Home.vue-Flow (setPendingUpload → /process/new),
 * aber ohne Hero-Headline-Cluster und ohne LandingPage-Layout.
 */
import Card from '../forms/Card.vue'
import AiModelPicker from '../forms/AiModelPicker.vue'
import Button from '../forms/Button.vue'
import IconPlus from '../shell/icons/IconPlus.vue'
import RunBudgetForm from '../run-budget/RunBudgetForm.vue'
import PreflightEstimateCard from '../run-budget/PreflightEstimateCard.vue'
import {
  ALLOWED,
  DOCUMENT_ROLES,
  NUM_AGENTS_MAX,
  NUM_ROUNDS_MAX,
  NUM_ROUNDS_MIN,
  formatBytes,
  useHeroNewRunState,
} from './heroNewRunHelpers'

const {
  files, documentRoles, isDragOver, fileInput, errorMsg, operatorAccess,
  selectedProfileId, selectedModel, language, simulationRequirement,
  numAgents, numRounds, budget, estimate, estimateLoading, estimateError, refreshEstimate,
  numAgentsMin, showAgentsWarning, profileOptions, canSubmit, disabledHint,
  onPickClick, onPickKey, onFiles, onDrop, onDragOver, onDragLeave,
  removeFile, onPickRole, onPickModel, onPickProfile, startSimulation,
} = useHeroNewRunState()
</script>

<template>
  <Card :title="$t('dashboard.hero.title')" :subtitle="$t('dashboard.hero.subtitle')">
    <div class="hero-grid">
      <!-- Zone 1: Quelle (Drop / Picker) -->
      <div class="hero-zone hero-source">
        <label class="hero-label">{{ $t('dashboard.hero.sourceLabel') }}</label>
        <div
          class="hero-drop"
          :class="{ 'hero-drop--over': isDragOver, 'hero-drop--filled': files.length > 0 }"
          role="button"
          tabindex="0"
          @click="onPickClick"
          @keydown="onPickKey"
          @drop="onDrop"
          @dragover="onDragOver"
          @dragleave="onDragLeave"
        >
          <template v-if="files.length === 0">
            <IconPlus :size="18" :stroke="1.6" class="hero-drop__icon" />
            <span class="hero-drop__title">{{ $t('dashboard.hero.dropHint') }}</span>
            <span class="hero-drop__formats">{{ ALLOWED.join('  ·  ') }}</span>
          </template>
          <template v-else>
            <ul class="hero-files">
              <li v-for="(f, i) in files" :key="`${f.name}-${i}`" class="hero-file">
                <span class="hero-file__name">{{ f.name }}</span>
                <select
                  class="hero-file__role"
                  :aria-label="`${$t('dashboard.hero.documentRoleLabel')}: ${f.name}`"
                  :value="documentRoles[i] ?? 'domain_fact'"
                  @click.stop
                  @keydown.stop
                  @change="onPickRole(i, $event)"
                >
                  <option v-for="role in DOCUMENT_ROLES" :key="role" :value="role">
                    {{ $t(`dashboard.hero.documentRoles.${role}`) }}
                  </option>
                </select>
                <span class="hero-file__size">{{ formatBytes(f.size) }}</span>
                <button
                  type="button"
                  class="hero-file__remove"
                  :aria-label="$t('common.delete')"
                  @click.stop="removeFile(i)"
                >
                  ✕
                </button>
              </li>
            </ul>
          </template>
        </div>
        <input
          ref="fileInput"
          type="file"
          class="hero-input-hidden"
          :accept="ALLOWED.join(',')"
          multiple
          @change="onFiles"
        />
      </div>

      <!-- Zone 2: Model + Sprache -->
      <div class="hero-zone hero-config">
        <div v-if="operatorAccess" class="hero-field">
          <label class="hero-label" for="hero-profile">
            {{ $t('dashboard.hero.profileLabel') }}
          </label>
          <select
            id="hero-profile"
            class="hero-select"
            :value="selectedProfileId ?? ''"
            @change="onPickProfile"
          >
            <option value="">
              {{ $t('dashboard.hero.profileNone') }}
            </option>
            <option v-for="opt in profileOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
        <div v-if="!selectedProfileId" class="hero-field">
          <label class="hero-label">{{ $t('dashboard.hero.modelLabel') }}</label>
          <AiModelPicker
            :model-value="selectedModel"
            :placeholder="$t('dashboard.hero.modelPlaceholder')"
            mode="chat"
            @update:model-value="onPickModel"
          />
        </div>
        <div class="hero-field">
          <label class="hero-label" for="hero-lang">{{ $t('dashboard.hero.languageLabel') }}</label>
          <select id="hero-lang" v-model="language" class="hero-select">
            <option value="de">{{ $t('dashboard.hero.languageDe') }}</option>
            <option value="en">{{ $t('dashboard.hero.languageEn') }}</option>
          </select>
        </div>
        <div class="hero-field">
          <label class="hero-label" for="hero-num-agents">
            {{ $t('dashboard.hero.numAgentsLabel') }}
            <span class="hero-slider-value">{{ numAgents }}</span>
            <span v-if="showAgentsWarning" class="hero-small-sim-badge" :title="$t('dashboard.hero.smallSimActiveTooltip')">
              {{ $t('dashboard.hero.smallSimBadge') }}
            </span>
          </label>
          <input
            id="hero-num-agents"
            v-model.number="numAgents"
            type="range"
            :min="numAgentsMin"
            :max="NUM_AGENTS_MAX"
            step="1"
            class="hero-slider"
            :aria-valuenow="numAgents"
            :aria-valuemin="numAgentsMin"
            :aria-valuemax="NUM_AGENTS_MAX"
          />
          <div v-if="showAgentsWarning" class="hero-warning" role="alert">
            <span class="hero-warning__icon" aria-hidden="true">&#9888;</span>
            {{ $t('dashboard.hero.numAgentsWarning') }}
          </div>
        </div>
        <div class="hero-field">
          <label class="hero-label" for="hero-num-rounds">
            {{ $t('dashboard.hero.numRoundsLabel') }}
            <span class="hero-slider-value">{{ numRounds }}</span>
          </label>
          <input
            id="hero-num-rounds"
            v-model.number="numRounds"
            type="range"
            :min="NUM_ROUNDS_MIN"
            :max="NUM_ROUNDS_MAX"
            step="1"
            class="hero-slider"
            :aria-valuenow="numRounds"
            :aria-valuemin="NUM_ROUNDS_MIN"
            :aria-valuemax="NUM_ROUNDS_MAX"
          />
        </div>
        <div class="hero-field hero-field--full">
          <details class="hero-budget">
            <summary class="hero-label hero-budget__summary">
              {{ $t('runBudget.sectionTitle') }}
            </summary>
            <div class="hero-budget__body">
              <RunBudgetForm v-model="budget" />
              <PreflightEstimateCard
                :estimate="estimate"
                :loading="estimateLoading"
                :error="estimateError"
              />
              <div class="hero-budget__estimate-actions">
                <Button
                  variant="ghost"
                  size="sm"
                  :loading="estimateLoading"
                  @click="refreshEstimate"
                >
                  {{ $t('runBudget.estimateRefresh') }}
                </Button>
              </div>
            </div>
          </details>
        </div>
        <div class="hero-field hero-field--full">
          <label class="hero-label" for="hero-requirement">
            {{ $t('dashboard.hero.requirementLabel') }}
            <span class="hero-required">*</span>
          </label>
          <textarea
            id="hero-requirement"
            v-model="simulationRequirement"
            class="hero-textarea"
            :placeholder="$t('dashboard.hero.requirementPlaceholder')"
            rows="3"
          />
        </div>
      </div>

      <!-- Zone 3: Aktion -->
      <div class="hero-zone hero-action">
        <button
          type="button"
          class="hero-cta"
          :disabled="!canSubmit"
          :aria-disabled="!canSubmit"
          @click="startSimulation"
        >
          {{ $t('dashboard.hero.startCta') }}
        </button>
        <p v-if="!canSubmit" class="hero-hint">
          {{ disabledHint }}
        </p>
        <p v-if="errorMsg" class="hero-error">{{ errorMsg }}</p>
      </div>
    </div>
  </Card>
</template>

<style scoped>
.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 0.9fr);
  gap: 24px;
  align-items: stretch;
}

.hero-zone {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.hero-label {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

/* Drop-Zone */
.hero-drop {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px dashed var(--hairline-strong);
  border-radius: var(--r-5, 10px);
  padding: 22px;
  background: var(--surface-inset);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 80ms ease, border-color 80ms ease;
  min-height: 132px;
}

.hero-drop:hover {
  background: var(--surface-hover);
}

.hero-drop:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.hero-drop--over {
  background: var(--accent-tint-bg);
  border-color: var(--accent);
  color: var(--accent-tint-text);
}

.hero-drop--filled {
  align-items: stretch;
  justify-content: flex-start;
  padding: 12px;
  background: var(--surface-elevated);
  border-style: solid;
  border-color: var(--hairline);
}

.hero-drop__icon {
  color: var(--text-tertiary);
}

.hero-drop__title {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.hero-drop__formats {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
}

.hero-files {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hero-file {
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  align-items: center;
  gap: 12px;
  padding: 6px 8px;
  border-radius: var(--r-4, 8px);
  font-family: var(--font-sans);
  font-size: 13px;
}

.hero-file:hover {
  background: var(--surface-hover);
}

.hero-file__name {
  font-family: var(--font-mono);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hero-file__role {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--surface-base, transparent);
  border: 1px solid var(--border-subtle, currentColor);
  border-radius: var(--r-3, 6px);
  padding: 2px 6px;
  max-width: 12rem;
}

.hero-file__size {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.hero-file__remove {
  background: transparent;
  border: 0;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 6px;
  border-radius: var(--r-3, 6px);
}

.hero-file__remove:hover {
  background: var(--surface-pressed);
  color: var(--text-secondary);
}

.hero-input-hidden {
  display: none;
}

/* Config */
.hero-config {
  justify-content: center;
}

.hero-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hero-select {
  font-family: var(--font-sans);
  font-size: 14px;
  padding: 9px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated);
  color: var(--text-primary);
  appearance: none;
  background-image: linear-gradient(45deg, transparent 50%, var(--text-tertiary) 50%),
                    linear-gradient(135deg, var(--text-tertiary) 50%, transparent 50%);
  background-position: calc(100% - 14px) 50%, calc(100% - 9px) 50%;
  background-size: 5px 5px;
  background-repeat: no-repeat;
  padding-right: 28px;
}

.hero-select:hover {
  border-color: var(--hairline-strong);
}

.hero-select:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}

/* Aktion */
.hero-action {
  justify-content: center;
  align-items: stretch;
}

.hero-cta {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.005em;
  background: var(--accent);
  color: var(--text-on-accent);
  border: 0;
  border-radius: var(--r-5, 10px);
  padding: 12px 18px;
  cursor: pointer;
  transition: background 80ms ease;
}

.hero-cta:hover:not(:disabled) {
  background: var(--accent-hover);
}

.hero-cta:active:not(:disabled) {
  background: var(--accent-pressed);
}

.hero-cta:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.hero-cta:disabled {
  background: var(--gray-4);
  color: var(--text-quaternary);
  cursor: not-allowed;
}

.hero-hint {
  margin: 8px 0 0;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
}

.hero-error {
  margin: 8px 0 0;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--status-red);
  text-align: center;
}

@media (max-width: 900px) {
  .hero-grid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero-drop,
  .hero-cta,
  .hero-select,
  .hero-file__remove {
    transition: none;
  }
}

.hero-field--full {
  width: 100%;
}

/* Budget-Section (Issue #764): aufklappbarer Block in Zone 2 */
.hero-budget {
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-inset);
  padding: 10px 12px;
}

.hero-budget__summary {
  cursor: pointer;
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.hero-budget__summary::before {
  content: '▸';
  font-size: 10px;
  transition: transform 120ms ease;
}

.hero-budget[open] .hero-budget__summary::before {
  transform: rotate(90deg);
}

.hero-budget__summary:focus-visible {
  outline: none;
  border-radius: var(--r-3, 6px);
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.hero-budget__body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 12px;
}

.hero-budget__estimate-actions {
  display: flex;
  justify-content: flex-end;
}

@media (prefers-reduced-motion: reduce) {
  .hero-budget__summary::before {
    transition: none;
  }
}

/* Slider */
.hero-slider {
  width: 100%;
  accent-color: var(--accent);
  cursor: pointer;
  height: 4px;
}

.hero-slider-value {
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-left: 6px;
}

.hero-small-sim-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 6px;
  border: 1px solid var(--status-orange);
  border-radius: var(--r-pill);
  background: var(--status-orange-bg);
  color: var(--status-orange);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  cursor: help;
}

/* Warning-Badge */
.hero-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--status-orange);
  border-radius: var(--r-4, 8px);
  background: var(--status-orange-bg);
  color: var(--status-orange);
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
}

.hero-warning__icon {
  flex-shrink: 0;
  font-size: 13px;
}

.hero-required {
  color: var(--status-red);
  margin-left: 2px;
}
.hero-textarea {
  font-family: var(--font-sans);
  font-size: 14px;
  padding: 9px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated);
  color: var(--text-primary);
  resize: vertical;
  min-height: 72px;
  line-height: 1.5;
}
.hero-textarea:hover { border-color: var(--hairline-strong); }
.hero-textarea:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}
</style>
