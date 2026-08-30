import { reactive } from 'vue';
import { api, type MemoryFact } from '../../api/client';

export const memorySession = reactive({
  facts: [] as MemoryFact[],
  open: false,
  loading: false,
});

export async function refreshMemory(characterId: number) {
  if (!characterId) {
    memorySession.facts = [];
    return;
  }
  memorySession.loading = true;
  try {
    memorySession.facts = await api.listMemory(characterId);
  } catch {
    memorySession.facts = [];
  } finally {
    memorySession.loading = false;
  }
}
