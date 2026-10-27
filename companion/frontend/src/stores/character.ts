import { defineStore } from 'pinia';
import { api, type CharacterItem } from '../api/client';
import { stage, type ModelInfo } from '../engine/stage';
import { caster } from '../features/performance/caster';
import { repertoire } from '../features/performance/repertoire';
import { shots } from '../features/performance/shotConductor';
import { speechPlayer } from '../features/voice/tts';
import { useAssetsStore } from './assets';

let switchGen = 0;

/** 舞台和桌宠是两个窗口，切换会整页重开。当前角色只活在内存里的话，新窗口会落到列表第一位。 */
const CURRENT_KEY = 'companion.character.current';

function staleLoad(err: unknown) {
  const msg = err instanceof Error ? err.message : String(err);
  return msg.includes('已被更新的加载取代');
}

function readSavedId(): number {
  try {
    const n = Number(localStorage.getItem(CURRENT_KEY) || 0);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  } catch {
    return 0;
  }
}

function writeSavedId(id: number) {
  try {
    if (id > 0) localStorage.setItem(CURRENT_KEY, String(id));
    else localStorage.removeItem(CURRENT_KEY);
  } catch { /* 隐私模式 */ }
}

/** 窗口被拆掉之前再写一次，避免只停在内存里。 */
export function rememberCurrentCharacter() {
  try {
    const id = useCharacterStore().currentId;
    if (id > 0) writeSavedId(id);
  } catch { /* pinia 还没起来 */ }
}

export const useCharacterStore = defineStore('character', {
  state: () => ({
    list: [] as CharacterItem[],
    currentId: 0,
    modelInfo: null as ModelInfo | null,
    modelLoading: false,
    modelError: '',
  }),
  getters: {
    current: (s) => s.list.find((c) => c.id === s.currentId) ?? null,
  },
  actions: {
    async loadList() {
      this.list = await api.listCharacters();
      if (this.currentId && this.list.some((c) => c.id === this.currentId)) {
        writeSavedId(this.currentId);
        return;
      }
      const saved = readSavedId();
      const hit = this.list.find((c) => c.id === saved);
      const next = hit?.id ?? this.list[0]?.id ?? 0;
      this.currentId = next;
      if (next) writeSavedId(next);
      else writeSavedId(0);
    },
    async load() {
      await this.loadList();
      if (this.currentId) await this.switchTo(this.currentId);
    },
    async switchTo(id: number) {
      const char = this.list.find((c) => c.id === id);
      if (!char) return;
      // 换角色：中断旧角色的对话流、语音、动作和 BGM
      const { useChatStore } = await import('./chat');
      void useChatStore().cancelStream();
      speechPlayer.stop();
      stage.stopMotion();
      this.currentId = id;
      writeSavedId(id);
      try {
        const { tarotLayerOn } = await import('../features/tarot/gate');
        if (tarotLayerOn.value) {
          const { onCharacterSwitch } = await import('../features/tarot');
          await onCharacterSwitch();
        }
      } catch { /* 塔罗未触发过 */ }
      const assets = useAssetsStore();
      if (!assets.models.length) await assets.refresh();
      const model = assets.modelById(char.model_asset_id) ?? assets.models[0];
      if (!model) {
        this.modelError = '没有可用的模型资产';
        return;
      }
      const gen = ++switchGen;
      this.modelLoading = true;
      this.modelError = '';
      try {
        const info = await stage.loadModel(api.assetUrl(model));
        if (gen !== switchGen) return;
        this.modelInfo = info;
        caster.indexFrom(assets.motions, info.morphNames);
        shots.indexFrom(assets.cameras);
        repertoire.idleFavorite = char.idle_motion || '';
        stage.director.idlePicker = () => caster.pickIdleUrl();
        stage.director.onSpeakBeat = () => caster.onSpeakBeat();
        stage.director.onIdleBeat = () => caster.onIdleBeat();
        stage.director.onIdleCam = () => shots.idleLive();
        shots.setIdleMode('chat');
        shots.beginIdle();
      } catch (e) {
        if (gen !== switchGen || staleLoad(e)) return;
        const msg = e instanceof Error ? e.message : String(e);
        this.modelError = msg;
      } finally {
        if (gen === switchGen) this.modelLoading = false;
      }
    },
    async save(char: CharacterItem) {
      const saved = await api.updateCharacter(char);
      const idx = this.list.findIndex((c) => c.id === saved.id);
      if (idx !== -1) this.list[idx] = saved;
      if (saved.id === this.currentId) {
        // 模型可能被改绑，重新加载
        await this.switchTo(saved.id!);
      }
      return saved;
    },
    async create(char: Partial<CharacterItem>) {
      const created = await api.createCharacter(char);
      this.list.push(created);
      return created;
    },
    async remove(id: number) {
      await api.deleteCharacter(id);
      this.list = this.list.filter((c) => c.id !== id);
      if (this.currentId === id) {
        if (this.list.length) await this.switchTo(this.list[0].id!);
        else {
          this.currentId = 0;
          writeSavedId(0);
        }
      }
    },
  },
});
