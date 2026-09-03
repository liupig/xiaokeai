import { defineStore } from 'pinia';
import { api, type AssetItem, type DownloadTask } from '../api/client';
import { ensureDanceMusicLibrary } from '../features/assets/motionMeta';

export const useAssetsStore = defineStore('assets', {
  state: () => ({
    models: [] as AssetItem[],
    motions: [] as AssetItem[],
    cameras: [] as AssetItem[],
    tasks: [] as DownloadTask[],
    loading: false,
  }),
  getters: {
    modelById: (s) => (id: number) => s.models.find((m) => m.id === id),
    motionByName: (s) => (name: string) => s.motions.find((m) => m.name === name),
  },
  actions: {
    async refresh() {
      this.loading = true;
      try {
        const all = await api.listAssets();
        this.models = all.filter((a) => a.kind === 'model');
        this.motions = all.filter((a) => a.kind === 'motion');
        this.cameras = all.filter((a) => a.kind === 'camera');
        void ensureDanceMusicLibrary();
      } finally {
        this.loading = false;
      }
    },
    async importFile(file: File) {
      const created = await api.importAsset(file);
      await this.refresh();
      return created;
    },
    async remove(id: number, removeFiles = false) {
      await api.deleteAsset(id, removeFiles);
      await this.refresh();
    },
    async startDownload(url: string, category = '') {
      const { task_id } = await api.createDownload(url, category);
      this.pollTask(task_id);
      return task_id;
    },
    async recategorize() {
      const r = await api.recategorizeMotions();
      await this.refresh();
      return r.updated;
    },
    async setMotionCategory(id: number, category: string) {
      await api.updateAsset(id, { category });
      await this.refresh();
    },
    pollTask(taskId: string) {
      const timer = setInterval(async () => {
        try {
          const task = await api.getDownloadTask(taskId);
          const idx = this.tasks.findIndex((t) => t.id === taskId);
          if (idx === -1) this.tasks.unshift(task);
          else this.tasks[idx] = task;
          if (task.status === 'done' || task.status === 'error') {
            clearInterval(timer);
            if (task.status === 'done') await this.refresh();
          }
        } catch {
          clearInterval(timer);
        }
      }, 800);
    },
  },
});
