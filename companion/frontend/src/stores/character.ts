import { defineStore } from 'pinia';
import { api, type CharacterItem } from '../api/client';
import { stage, type ModelInfo } from '../engine/stage';
import { caster } from '../features/performance/caster';
import { repertoire } from '../features/performance/repertoire';
import { shots } from '../features/performance/shotConductor';
import { speechPlayer } from '../features/voice/tts';
import { useAssetsStore } from './assets';

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
      if (!this.currentId && this.list.length) {
        this.currentId = this.list[0].id!;
      }
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
      useChatStore().cancelStream();
      speechPlayer.stop();
      stage.stopMotion();
      this.currentId = id;
      const assets = useAssetsStore();
      if (!assets.models.length) await assets.refresh();
      const model = assets.modelById(char.model_asset_id) ?? assets.models[0];
      if (!model) {
        this.modelError = '没有可用的模型资产';
        return;
      }
      this.modelLoading = true;
      this.modelError = '';
      try {
        this.modelInfo = await stage.loadModel(api.assetUrl(model));
        caster.indexFrom(assets.motions, this.modelInfo.morphNames);
        shots.indexFrom(assets.cameras);
        repertoire.idleFavorite = char.idle_motion || '';
        stage.director.idlePicker = () => caster.pickIdleUrl();
        stage.director.onSpeakBeat = () => caster.onSpeakBeat();
        stage.director.onIdleBeat = () => caster.onIdleBeat();
        stage.director.onIdleCam = () => shots.idleLive();
        shots.setIdleMode('chat');
        shots.beginIdle();
      } catch (e) {
        this.modelError = String(e);
      } finally {
        this.modelLoading = false;
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
      if (this.currentId === id && this.list.length) {
        await this.switchTo(this.list[0].id!);
      }
    },
  },
});
