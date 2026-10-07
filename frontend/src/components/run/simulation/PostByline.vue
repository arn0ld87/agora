<script setup lang="ts">
/**
 * Kopfzeile eines Beitrags: Avatar, Name, „SIM"-Kennzeichen mit zugänglichem
 * Text „synthetische Äußerung", Zeit und Runde (#1801). Von Karten, Zeilen,
 * Faden und Baum gemeinsam genutzt.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PersonaAvatar from '@/components/v4/sim-feed/PersonaAvatar.vue'
import SimBadge from '@/components/v4/sim-feed/SimBadge.vue'
import type { FeedPost } from '@/composables/run/simulation/threads'
import { formatPostTime } from './feedFormat'

const props = defineProps<{ post: FeedPost }>()
const { t, locale } = useI18n()

const time = computed(() => formatPostTime(props.post.timestamp, locale.value))
</script>

<template>
  <div class="byline" data-testid="post-byline">
    <PersonaAvatar
      :persona-id="post.persona_id"
      :persona-name="post.persona_name"
      :voice-register="post.voice_register"
    />
    <span class="byline__name">{{ post.persona_name }}</span>
    <span class="byline__sim" data-testid="post-sim">
      <SimBadge aria-hidden="true" />
      <span class="sr-only">{{ t('views.run.simFeed.post.simText') }}</span>
    </span>
    <time class="byline__time" :datetime="post.timestamp">{{ time }}</time>
    <span v-if="post.round_num != null" class="byline__round">
      {{ t('views.run.simFeed.post.round', { round: post.round_num }) }}
    </span>
  </div>
</template>

<style scoped>
.byline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  min-width: 0;
  font-size: 13px;
}
.byline__name {
  font-weight: 650;
  color: var(--fg);
}
.byline__sim {
  display: inline-flex;
}
.byline__time,
.byline__round {
  color: var(--fg3);
  font-size: 12px;
}
</style>
