<script setup lang="ts">
/**
 * NewRunDialog — Startdialog „Neuer Lauf“ (#1799, Etappe 3, Bauplan §3.4).
 *
 * Ein Dialog, fünf Gruppen, kein Assistent: Frage, Graph, Personasatz, Modelle,
 * Umfang und Budget. Er liegt als Fenster über der zuletzt gezeigten Ansicht
 * (gleicher Mechanismus wie das Einstellungsfenster, siehe App.vue und
 * `isWindowRoute`).
 *
 * Was das Backend heute kann, steht hier ehrlich: Die Frage gehört zum Graphen,
 * „Ohne Graph“ und gespeicherte Personasätze gibt es noch nicht, ein Modell
 * oder Profil gilt für den Aufruf, dem es mitgegeben wird.
 */
import { RouterLink } from 'vue-router'
import {
  DialogClose,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import Button from '@/components/v4/forms/Button.vue'
import RunBudgetForm from '@/components/v4/run-budget/RunBudgetForm.vue'
import PreflightEstimateCard from '@/components/v4/run-budget/PreflightEstimateCard.vue'
import AgentCapControl from '@/components/step2/AgentCapControl.vue'
import ContestedQuestionField from '@/components/step2/ContestedQuestionField.vue'
import ActivityModeField from '@/components/step2/ActivityModeField.vue'
import SourceDropzone from './SourceDropzone.vue'
import { MAX_SIMULATION_DAYS } from '@/contracts/runParamsQuery'
import { MAX_ROUNDS, MIN_ROUNDS, graphLabel, useNewRunDialogState } from './newRunDialogHelpers'

const {
  t, id, operatorAccess,
  question, contestedQuestion, graphMode, selectedProjectId, files, documentRoles, fileError, graphsSource,
  personaMode, personaSets, selectedPersonaSetId, selectedPersonaSet, personaSetUsable, existingGraphs,
  useAgentCap, maxAgents, selectedProfileId, selectedModel, language, profileOptions,
  days, rounds, activityMode, budgetDefaults, budget, budgetChanged, estimate, estimateLoading, estimateError,
  onPickProfile, onPickModel, onBudgetUpdate, refreshEstimate,
  submit, uploadError, busy, agentsValid, daysValid, roundsValid, blockers, canSubmit,
  onCreateOnly, onStart, close, restoreFocus, questionText, phaseText, startLabel,
} = useNewRunDialogState()
</script>

<template>
  <DialogRoot :open="true" @update:open="(open: boolean) => { if (!open) close() }">
    <DialogPortal>
      <DialogOverlay class="nr-overlay" />
      <DialogContent
        class="nr"
        :aria-describedby="undefined"
        data-testid="new-run-dialog"
        @close-auto-focus="restoreFocus"
      >
        <header class="nr__header">
          <DialogTitle class="nr__title">{{ t('views.newRun.title') }}</DialogTitle>
          <DialogClose class="nr__close" :aria-label="t('views.newRun.close')">
            <span aria-hidden="true">✕</span>
          </DialogClose>
        </header>

        <form class="nr__body" novalidate @submit.prevent="onStart">
          <!-- 1. Frage -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.question.legend') }}</legend>
            <div class="nr__field">
              <label class="nr__label" :for="id('question')">
                {{ t('views.newRun.question.label') }}
                <span v-if="graphMode === 'new' || personaMode === 'set'" class="nr__required" aria-hidden="true">*</span>
              </label>
              <textarea
                :id="id('question')"
                class="nr__textarea"
                rows="3"
                :required="graphMode === 'new' || personaMode === 'set'"
                :readonly="graphMode === 'existing'"
                :value="questionText"
                :placeholder="t('dashboard.hero.requirementPlaceholder')"
                :aria-describedby="graphMode === 'existing' ? id('question-note') : undefined"
                data-testid="new-run-question"
                @input="question = ($event.target as HTMLTextAreaElement).value"
              />
              <p v-if="graphMode === 'existing'" :id="id('question-note')" class="nr__hint">
                {{ t('views.newRun.question.belongsToGraph') }}
              </p>
            </div>
            <ContestedQuestionField v-model="contestedQuestion" :is-preparing="busy || graphMode === 'new'" />
            <p v-if="graphMode === 'new'" class="nr__hint">{{ t('views.newRun.question.contestedLater') }}</p>
          </fieldset>

          <!-- 2. Graph -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.graph.legend') }}</legend>

            <div class="nr__radio">
              <input
                :id="id('graph-existing')"
                v-model="graphMode"
                type="radio"
                name="graph-mode"
                value="existing"
                :disabled="!existingGraphs"
                :aria-describedby="!existingGraphs ? id('graph-existing-why') : undefined"
              />
              <div class="nr__radio-text">
                <label :for="id('graph-existing')">{{ t('views.newRun.graph.existing') }}</label>
                <p v-if="!existingGraphs" :id="id('graph-existing-why')" class="nr__hint">
                  {{ graphsSource.loading.value ? t('views.newRun.graph.loading') : (graphsSource.error.value || t('views.newRun.graph.noneYet')) }}
                </p>
                <template v-else>
                  <label class="nr__sr" :for="id('graph-select')">{{ t('views.newRun.graph.selectLabel') }}</label>
                  <select
                    :id="id('graph-select')"
                    v-model="selectedProjectId"
                    class="nr__select"
                    :disabled="graphMode !== 'existing'"
                    data-testid="new-run-graph-select"
                  >
                    <option v-for="g in graphsSource.graphs.value" :key="g.projectId" :value="g.projectId">
                      {{ graphLabel(g) }}
                    </option>
                  </select>
                </template>
                <p v-if="graphsSource.rejected.value > 0" class="nr__hint" role="status">
                  {{ t('views.newRun.graph.rejected', { n: graphsSource.rejected.value }) }}
                </p>
              </div>
            </div>

            <div class="nr__radio">
              <input
                :id="id('graph-new')"
                v-model="graphMode"
                type="radio"
                name="graph-mode"
                value="new"
              />
              <div class="nr__radio-text">
                <label :for="id('graph-new')">{{ t('views.newRun.graph.fromSource') }}</label>
                <SourceDropzone
                  v-if="graphMode === 'new'"
                  v-model:files="files"
                  v-model:document-roles="documentRoles"
                  :disabled="busy"
                  @rejected="fileError = t('errors.fileTypeNotAllowed')"
                  @accepted="fileError = ''"
                />
                <p v-if="fileError" class="nr__error" role="alert">{{ fileError }}</p>
              </div>
            </div>

            <div class="nr__radio nr__radio--off">
              <input
                :id="id('graph-none')"
                type="radio"
                name="graph-mode"
                value="none"
                disabled
                :aria-describedby="id('graph-none-why')"
              />
              <div class="nr__radio-text">
                <label :for="id('graph-none')">{{ t('views.newRun.graph.none') }}</label>
                <p :id="id('graph-none-why')" class="nr__hint">{{ t('views.newRun.graph.noneWhy') }}</p>
              </div>
            </div>
          </fieldset>

          <!-- 3. Personasatz -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.personas.legend') }}</legend>
            <div class="nr__radio">
              <input :id="id('personas-generate')" type="radio" name="persona-mode" value="generate" checked />
              <div class="nr__radio-text">
                <label :for="id('personas-generate')">{{ t('views.newRun.personas.generate') }}</label>
                <AgentCapControl
                  v-model:use-agent-cap="useAgentCap"
                  v-model:max-agents="maxAgents"
                  :is-preparing="busy"
                />
                <p v-if="graphMode === 'new'" class="nr__hint">{{ t('views.newRun.personas.laterWithSource') }}</p>
              </div>
            </div>
            <!-- Vor Etappe 7 stand hier ein dauerhaft deaktiviertes Feld mit
                 dem Hinweis, der Satz komme spaeter. Jetzt waehlt es einen
                 Satz aus der Bibliothek; der Lauf entsteht ohne Graph
                 (Maintainer-Entscheid 07.10.). -->
            <div class="nr__radio" :class="{ 'nr__radio--off': personaMode !== 'set' }">
              <input
                :id="id('personas-set')"
                v-model="personaMode"
                type="radio"
                name="persona-mode"
                value="set"
                :disabled="busy"
                :aria-describedby="id('personas-set-why')"
              />
              <div class="nr__radio-text">
                <label :for="id('personas-set')">{{ t('views.newRun.personas.set') }}</label>
                <p :id="id('personas-set-why')" class="nr__hint">
                  {{ t('views.newRun.personas.setWhy') }}
                </p>
                <template v-if="personaMode === 'set'">
                  <label class="nr__label" :for="id('persona-set-picker')">
                    {{ t('views.newRun.personas.chooseSet') }}
                  </label>
                  <select
                    :id="id('persona-set-picker')"
                    class="nr__select"
                    v-model="selectedPersonaSetId"
                    :disabled="busy || personaSets.loading.value"
                    data-testid="new-run-persona-set"
                  >
                    <option value="">
                      {{ personaSets.loading.value
                        ? t('views.newRun.personas.loadingSets')
                        : t('views.newRun.personas.noSetChosen') }}
                    </option>
                    <option v-for="opt in personaSetUsable" :key="opt.id" :value="opt.id">
                      {{ opt.name }} ({{ t('views.newRun.personas.count', { n: opt.entry_count }) }})
                    </option>
                  </select>
                  <p v-if="personaSetUsable.length === 0 && !personaSets.loading.value" class="nr__hint">
                    {{ t('views.newRun.personas.noSetsYet') }}
                  </p>
                  <p v-if="selectedPersonaSet" class="nr__hint">
                    {{ t('views.newRun.personas.noGraphNotice') }}
                  </p>
                </template>
              </div>
            </div>
          </fieldset>

          <!-- 4. Modelle -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.models.legend') }}</legend>
            <div v-if="operatorAccess" class="nr__field">
              <label class="nr__label" :for="id('profile')">{{ t('dashboard.hero.profileLabel') }}</label>
              <select
                :id="id('profile')"
                class="nr__select"
                :value="selectedProfileId ?? ''"
                data-testid="new-run-profile"
                @change="onPickProfile"
              >
                <option value="">{{ t('dashboard.hero.profileNone') }}</option>
                <option v-for="opt in profileOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </div>
            <div v-if="!selectedProfileId" class="nr__field">
              <span :id="id('model-label')" class="nr__label">{{ t('dashboard.hero.modelLabel') }}</span>
              <AiModelPicker
                :model-value="selectedModel"
                :placeholder="t('dashboard.hero.modelPlaceholder')"
                mode="chat"
                @update:model-value="onPickModel"
              />
            </div>
            <div class="nr__field">
              <label class="nr__label" :for="id('lang')">{{ t('dashboard.hero.languageLabel') }}</label>
              <select :id="id('lang')" v-model="language" class="nr__select">
                <option value="de">{{ t('dashboard.hero.languageDe') }}</option>
                <option value="en">{{ t('dashboard.hero.languageEn') }}</option>
              </select>
            </div>
            <p class="nr__hint">{{ t('views.newRun.models.scope') }}</p>
          </fieldset>

          <!-- 5. Umfang und Budget -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.scope.legend') }}</legend>
            <div class="nr__row">
              <div class="nr__field">
                <label class="nr__label" :for="id('days')">{{ t('views.newRun.scope.days') }}</label>
                <input
                  :id="id('days')"
                  v-model.number="days"
                  class="nr__number"
                  type="number"
                  min="1"
                  :max="MAX_SIMULATION_DAYS"
                  step="1"
                  :aria-invalid="daysValid ? undefined : 'true'"
                />
              </div>
              <div class="nr__field">
                <label class="nr__label" :for="id('rounds')">{{ t('views.newRun.scope.rounds') }}</label>
                <input
                  :id="id('rounds')"
                  v-model.number="rounds"
                  class="nr__number"
                  type="number"
                  :min="MIN_ROUNDS"
                  :max="MAX_ROUNDS"
                  step="1"
                  :aria-invalid="roundsValid ? undefined : 'true'"
                />
              </div>
            </div>
            <ActivityModeField v-model="activityMode" :is-preparing="busy" />
            <p v-if="graphMode === 'new'" class="nr__hint">{{ t('views.newRun.scope.activityLater') }}</p>

            <div class="nr__field">
              <span class="nr__label">{{ t('runBudget.sectionTitle') }}</span>
              <p v-if="budgetDefaults.state.value === 'unavailable'" class="nr__hint" data-testid="new-run-budget-unavailable">
                {{ t('views.newRun.scope.budgetUnavailable') }}
              </p>
              <RunBudgetForm :model-value="budget" :disabled="busy" @update:model-value="onBudgetUpdate" />
              <p v-if="budgetChanged" class="nr__hint" data-testid="new-run-budget-replaces">
                {{ t('views.newRun.scope.budgetReplaces') }}
              </p>
            </div>

            <PreflightEstimateCard :estimate="estimate" :loading="estimateLoading" :error="estimateError" />
            <div>
              <Button
                variant="ghost"
                size="sm"
                :loading="estimateLoading"
                :disabled="!useAgentCap || !agentsValid"
                @click="refreshEstimate"
              >
                {{ t('runBudget.estimateRefresh') }}
              </Button>
              <p v-if="!useAgentCap" class="nr__hint">{{ t('views.newRun.scope.estimateNeedsCap') }}</p>
              <p v-else class="nr__hint">{{ t('views.newRun.scope.estimateBasis', { agents: maxAgents, rounds }) }}</p>
            </div>
          </fieldset>

          <!-- Hinweise, Fehler, Fortschritt -->
          <div class="nr__status">
            <ul v-if="blockers.length > 0" class="nr__blockers" data-testid="new-run-blockers">
              <li v-for="b in blockers" :key="b">{{ b }}</li>
            </ul>
            <p v-if="busy" class="nr__progress" role="status" data-testid="new-run-progress">{{ phaseText }}</p>
            <p v-if="submit.error.value" class="nr__error" role="alert" data-testid="new-run-error">
              {{ submit.error.value }}
            </p>
            <RouterLink
              v-if="submit.createdSimulationId.value && submit.error.value"
              class="nr__link"
              data-testid="new-run-created-link"
              :to="{ name: 'RunOverview', params: { simulationId: submit.createdSimulationId.value } }"
            >
              {{ t('views.newRun.errors.openCreated') }}
            </RouterLink>
            <p v-if="uploadError" class="nr__error" role="alert">{{ uploadError }}</p>
          </div>

          <footer class="nr__footer">
            <button type="button" class="nr__btn" @click="close">{{ t('views.newRun.actions.cancel') }}</button>
            <div class="nr__create">
              <button
                type="button"
                class="nr__btn"
                :disabled="!canSubmit || graphMode !== 'existing'"
                :aria-describedby="graphMode === 'new' ? id('create-why') : undefined"
                data-testid="new-run-create-only"
                @click="onCreateOnly"
              >
                {{ t('views.newRun.actions.createOnly') }}
              </button>
              <p v-if="graphMode === 'new'" :id="id('create-why')" class="nr__hint">
                {{ t('views.newRun.actions.createOnlyWhy') }}
              </p>
            </div>
            <button
              type="submit"
              class="nr__btn nr__btn--primary"
              :disabled="!canSubmit"
              data-testid="new-run-start"
            >
              {{ startLabel }}
            </button>
          </footer>
        </form>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.nr-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--scrim);
}

.nr {
  position: fixed;
  z-index: 201;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: min(760px, calc(100vw - 32px));
  max-height: calc(100dvh - 32px);
  display: flex;
  flex-direction: column;
  background: var(--s2);
  color: var(--fg);
  border-radius: var(--ag-r-16);
  box-shadow: var(--shadow-dlg);
  overflow: hidden;
  font-family: var(--ag-font-sans);
}

.nr__header {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 16px 8px 24px;
}

.nr__title {
  flex: 1;
  margin: 0;
  font-size: 18px;
  font-weight: 650;
}

.nr__close {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 15px;
  cursor: pointer;
}

.nr__close:hover {
  background: var(--s3);
}

.nr__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.nr__group {
  min-width: 0;
  margin: 0;
  padding: 12px 14px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.nr__legend {
  padding: 0 6px;
  font-size: 13.5px;
  font-weight: 650;
}

.nr__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.nr__row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.nr__label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--fg2);
}

.nr__required {
  color: var(--status-error);
}

.nr__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.nr__textarea,
.nr__select,
.nr__number {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--field);
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
}

.nr__textarea {
  resize: vertical;
}

.nr__textarea[readonly] {
  background: var(--s1);
  color: var(--fg2);
}

.nr__number {
  width: 120px;
}

.nr__textarea:focus-visible,
.nr__select:focus-visible,
.nr__number:focus-visible,
.nr__close:focus-visible,
.nr__btn:focus-visible,
.nr__link:focus-visible,
.nr__radio input:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.nr__radio {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.nr__radio input {
  margin-top: 3px;
}

.nr__radio-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13.5px;
}

.nr__radio--off .nr__radio-text > label {
  color: var(--fg2);
}

.nr__hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--fg2);
}

.nr__error {
  margin: 0;
  padding: 8px 10px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--status-error);
  font-size: 13px;
}

.nr__status {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nr__blockers {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  color: var(--fg2);
}

.nr__progress {
  margin: 0;
  font-size: 13px;
}

.nr__link {
  align-self: flex-start;
  color: var(--acc-text);
  font-size: 13px;
}

.nr__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 10px;
}

.nr__footer > :first-child {
  margin-right: auto;
}

.nr__create {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 260px;
}

.nr__btn {
  height: 34px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
  cursor: pointer;
}

.nr__btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.nr__btn--primary {
  border-color: transparent;
  background: var(--acc);
  color: var(--on-acc);
}

@media (max-width: 767px) {
  .nr {
    width: calc(100vw - 16px);
    max-height: calc(100dvh - 16px);
  }

  .nr__body {
    padding: 8px 14px 16px;
  }

  .nr__row {
    flex-direction: column;
    gap: 12px;
  }

  .nr__number {
    width: 100%;
  }

  .nr__footer {
    flex-direction: column;
    align-items: stretch;
  }

  .nr__footer > :first-child {
    margin-right: 0;
  }

  .nr__create {
    max-width: none;
  }
}
</style>
