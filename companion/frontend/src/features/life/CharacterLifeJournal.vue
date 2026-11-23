<script setup lang="ts">
import { ref, watch } from 'vue';
import { NSwitch } from 'naive-ui';
import { api, type CharacterLifeJournal } from '../../api/client';
import { t } from '../../i18n';
import { useCharacterStore } from '../../stores/character';

const props = defineProps<{ show: boolean }>();
const characters = useCharacterStore();
const journal = ref<CharacterLifeJournal | null>(null);
const status = ref<'loading' | 'disabled' | 'ready' | 'error'>('loading');
const savingId = ref<number>();
const saveErrorId = ref<number>();
const reload = ref(0);
const sections = ['journal_plan', 'journal_month'] as const;

watch(
  () => [props.show, characters.currentId, characters.current?.character_life_enabled, reload.value] as const,
  async ([visible, id, enabled], _previous, cleanup) => {
    journal.value = null;
    if (!visible || !id) return;
    status.value = enabled ? 'loading' : 'disabled';
    if (!enabled) return;
    const controller = new AbortController();
    cleanup(() => controller.abort());
    try {
      const result = await api.characterLifeJournal(id, controller.signal);
      if (controller.signal.aborted) return;
      journal.value = result.journal;
      status.value = result.enabled ? 'ready' : 'disabled';
    } catch {
      if (!controller.signal.aborted) status.value = 'error';
    }
  },
  { immediate: true },
);

async function toggle(enabled: boolean) {
  const id = characters.currentId;
  if (!id || savingId.value) return;
  savingId.value = id;
  saveErrorId.value = undefined;
  try {
    const result = await api.setCharacterLifeEnabled(id, enabled);
    const character = characters.list.find((item) => item.id === id);
    if (character) character.character_life_enabled = result.enabled;
  } catch {
    saveErrorId.value = id;
  } finally {
    savingId.value = undefined;
  }
}
</script>

<template>
  <section v-if="characters.current" class="journal">
    <header class="journal-header">
      <div>
        <h2>{{ t('char.journal.title') }}</h2>
        <p>{{ characters.current.name }}</p>
      </div>
      <n-switch :value="characters.current.character_life_enabled === true"
                :loading="savingId === characters.currentId" :disabled="savingId !== undefined"
                :aria-label="t('mod.characterLife')" @update:value="toggle" />
    </header>

    <p v-if="saveErrorId === characters.currentId" role="alert">{{ t('char.journal.saveError') }}</p>
    <div v-if="status === 'error'" role="status">
      <p>{{ t('char.journal.error') }}</p>
      <button type="button" @click="reload++">{{ t('char.journal.retry') }}</button>
    </div>
    <p v-else-if="status !== 'ready'" role="status">{{ t('char.journal.' + status) }}</p>
    <template v-else-if="journal && (journal.journal_today || journal.journal_trace || sections.some(key => journal?.[key]) || journal.milestones?.length || journal.entries?.length || journal.discussed.length)">
      <article v-if="journal.journal_today || journal.journal_trace" class="journal-entry">
        <time :datetime="journal.as_of">{{ journal.as_of }}</time>
        <h3 v-if="journal.journal_title">{{ journal.journal_title }}</h3>
        <p v-if="journal.journal_today">{{ journal.journal_today }}</p>
        <blockquote v-if="journal.journal_trace" class="journal-trace">{{ journal.journal_trace }}</blockquote>
      </article>
      <time v-else :datetime="journal.as_of">{{ journal.as_of }}</time>
      <template v-for="key in sections" :key="key">
        <section v-if="journal[key]">
          <h3>{{ t('char.journal.' + key) }}</h3>
          <p>{{ journal[key] }}</p>
          <small v-if="key === 'journal_plan' && journal.follow_up_on" class="journal-follow-up">
            {{ t('char.journal.followUp', { date: journal.follow_up_on }) }}
          </small>
        </section>
      </template>
      <section v-if="journal.milestones?.some(entry => entry.text !== journal?.journal_month)">
        <h3>{{ t('char.journal.milestones') }}</h3>
        <ul>
          <template v-for="entry in [...journal.milestones].reverse()" :key="entry.date + entry.text">
            <li v-if="entry.text !== journal.journal_month">
              <time :datetime="entry.date">{{ entry.date }}</time> {{ entry.text }}
            </li>
          </template>
        </ul>
      </section>
      <section v-if="journal.discussed.length">
        <h3>{{ t('char.journal.discussed') }}</h3>
        <ul>
          <li v-for="entry in journal.discussed" :key="entry.text">
            <time :datetime="entry.date">{{ entry.date }}</time> {{ entry.text }}
          </li>
        </ul>
      </section>
      <details v-if="journal.entries?.length" class="journal-history">
        <summary>{{ t('char.journal.entries') }}</summary>
        <article v-for="entry in [...journal.entries].reverse()" :key="entry.date">
          <time :datetime="entry.date">{{ entry.date }}</time>
          <h3 v-if="entry.title">{{ entry.title }}</h3>
          <p>{{ entry.text }}</p>
        </article>
      </details>
    </template>
    <p v-else role="status">{{ t('char.journal.empty') }}</p>
  </section>
</template>

<style scoped>
.journal {
  display: grid;
  gap: 16px;
  padding: clamp(16px, 4vw, 26px);
  border: 1px solid #d4b47a2e;
  border-radius: 18px;
  background: linear-gradient(135deg, #49352c, #271f1c);
  overflow-wrap: anywhere;
}
.journal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ffffff16;
}
.journal-header h2 {
  margin: 0 0 4px;
  font: 500 25px/1.2 Georgia, 'Noto Serif SC', serif;
}
.journal-header p, .journal time {
  color: #d2bba8;
}
.journal time {
  font-size: 12px;
}
.journal-entry {
  padding: clamp(16px, 4vw, 24px);
  border-radius: 6px 12px 12px 6px;
  border-left: 2px solid #d6ad7f;
  background: #eedbc3;
  color: #34251e;
}
.journal-entry time {
  color: #6e5545;
}
.journal .journal-entry h3 {
  margin: 6px 0 10px;
  font: 500 23px/1.3 Georgia, 'Noto Serif SC', serif;
  color: #403028;
}
.journal .journal-entry p {
  margin-top: 6px;
  line-height: 1.85;
}
.journal-trace {
  width: fit-content;
  max-width: 100%;
  margin: 18px 0 0;
  padding: 10px 14px;
  border: 1px dashed #986c54;
  background: #f9ead6;
  font-family: Georgia, 'Noto Serif SC', serif;
  white-space: pre-wrap;
}
.journal-follow-up {
  display: block;
  margin-top: 6px;
  color: #dcc0a6;
}
.journal-history summary {
  cursor: pointer;
  color: #efcfaa;
}
.journal-history article {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #ffffff16;
}
.journal h3 {
  margin: 0 0 4px;
  font-size: 14px;
  color: #efcfaa;
}
.journal p, .journal ul {
  margin: 0;
  line-height: 1.65;
}
.journal ul {
  padding-inline-start: 18px;
}
.journal button {
  margin-top: 8px;
  padding: 6px 12px;
  border: 1px solid #ae8f7055;
  border-radius: 9px;
  background: #41342f;
  color: #fae8d2;
  cursor: pointer;
}
</style>
