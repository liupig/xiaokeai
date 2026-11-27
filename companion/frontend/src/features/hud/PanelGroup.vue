<script setup lang="ts">
defineProps<{
  title: string;
  collapsible?: boolean;
  tone?: 'rose' | 'violet' | 'teal' | 'amber' | 'blue';
}>();
</script>

<template>
  <component :is="collapsible ? 'details' : 'section'" class="panel-group" :data-tone="tone">
    <summary v-if="collapsible" class="group-heading">{{ title }}</summary>
    <h4 v-else class="group-heading">{{ title }}</h4>
    <div class="group-body"><slot /></div>
  </component>
</template>

<style scoped>
.panel-group {
  --group-accent: var(--panel-accent);
  min-width: 0;
  border: 1px solid var(--panel-line);
  border-inline-start-color: color-mix(in srgb, var(--group-accent) 55%, transparent);
  border-radius: 13px;
  background: var(--panel-card);
}
.panel-group[data-tone="rose"] { --group-accent: #ecc1d6; }
.panel-group[data-tone="violet"] { --group-accent: #d5c7f5; }
.panel-group[data-tone="teal"] { --group-accent: #b9e0d3; }
.panel-group[data-tone="amber"] { --group-accent: #efce9f; }
.panel-group[data-tone="blue"] { --group-accent: #bbd7f1; }
.group-heading {
  padding: 12px 15px;
  color: var(--group-accent);
  background: color-mix(in srgb, var(--group-accent) 10%, transparent);
  border-radius: 12px 12px 0 0;
  font-size: 13px;
  font-weight: 650;
  overflow-wrap: anywhere;
}
summary.group-heading { cursor: pointer; }
details:not([open]) > .group-heading { border-radius: 12px; }
summary.group-heading:hover { background: color-mix(in srgb, var(--group-accent) 17%, transparent); }
summary.group-heading:focus-visible {
  outline: 2px solid var(--panel-accent);
  outline-offset: -2px;
  border-radius: 12px;
}
.group-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  padding: 12px 15px 15px;
  border-top: 1px solid var(--panel-line);
}
</style>
