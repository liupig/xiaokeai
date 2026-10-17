import { reactive } from 'vue';
import { api, type MemoryEpisode, type MemoryFact, type PinnedLine } from '../../api/client';

export const memorySession = reactive({
  facts: [] as MemoryFact[],
  pins: [] as PinnedLine[],
  episodes: [] as MemoryEpisode[],
  open: false,
  loading: false,
});

export async function refreshMemory(characterId: number) {
  if (!characterId) {
    memorySession.facts = [];
    memorySession.pins = [];
    memorySession.episodes = [];
    return;
  }
  memorySession.loading = true;
  try {
    const [facts, pins, episodes] = await Promise.all([
      api.listMemory(characterId).catch(() => [] as MemoryFact[]),
      api.listPins(characterId).catch(() => [] as PinnedLine[]),
      api.listEpisodes(characterId).catch(() => [] as MemoryEpisode[]),
    ]);
    memorySession.facts = facts;
    memorySession.pins = pins;
    memorySession.episodes = episodes;
  } finally {
    memorySession.loading = false;
  }
}
