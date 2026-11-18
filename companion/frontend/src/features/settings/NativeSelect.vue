<script setup lang="ts">
type Option = { label: string; value: string | number | boolean | null };

const props = defineProps<{
  value: string | number | boolean | null;
  options: Option[];
}>();
const emit = defineEmits<{ 'update:value': [value: string | number | boolean | null] }>();

function onChange(event: Event) {
  const raw = (event.target as HTMLSelectElement).value;
  const option = props.options.find((row) => String(row.value) === raw);
  if (option) emit('update:value', option.value);
}
</script>

<template>
  <select class="settings-native-select" :value="String(value ?? '')" @change="onChange">
    <option v-for="option in options" :key="String(option.value)" :value="String(option.value ?? '')">
      {{ option.label }}
    </option>
  </select>
</template>

<style scoped>
.settings-native-select {
  box-sizing: border-box;
  width: 100%;
  min-height: 34px;
  padding: 6px 30px 6px 10px;
  color: var(--n-text-color, inherit);
  background: var(--n-color, rgba(255, 255, 255, 0.08));
  border: 1px solid var(--n-border-color, rgba(255, 255, 255, 0.16));
  border-radius: 4px;
  outline: none;
}
.settings-native-select:focus {
  border-color: #63e2b7;
}
.settings-native-select option {
  color: #222;
  background: #fff;
}
</style>
