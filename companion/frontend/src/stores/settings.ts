import { defineStore } from 'pinia';
import { api } from '../api/client';
import { stage } from '../engine/stage';
import {
  DEFAULT_DUPLEX_REMAIN_SEC,
  normalizeDuplexCmd,
  speechPlayer,
  type DuplexCmd,
} from '../features/voice/tts';
import {
  DEFAULT_DUPLEX_DELAYED_SEC,
  DEFAULT_DUPLEX_GOODBYE_SEC,
  DEFAULT_DUPLEX_PROACTIVE_SEC,
  DEFAULT_DUPLEX_SESSION_MAX_MIN,
} from '../features/voice/duplex';

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    loaded: false,
    llm_env: false,
    llm_local: false,
    llm: {
      base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', api_key: '',
      model: 'qwen-plus', temperature: 0.85, top_p: 1.0,
      max_tokens: 0, thinking: 'default',
    },
    tts: { engine: 'qwen' as 'cosy' | 'edge' | 'qwen' | 'browser' | 'off',
           voice: 'Vivian', rate: '+0%', qwen_size: '0.6b' as '0.6b' | '1.7b',
           qwen_style: 'yujie' as string, qwen_instruct: '',
           duplex_cmd: 'interrupt_or_queue' as DuplexCmd,
           duplex_remain_sec: DEFAULT_DUPLEX_REMAIN_SEC,
           duplex_delayed_sec: DEFAULT_DUPLEX_DELAYED_SEC,
           duplex_proactive_sec: DEFAULT_DUPLEX_PROACTIVE_SEC,
           duplex_goodbye_sec: DEFAULT_DUPLEX_GOODBYE_SEC,
           duplex_session_max_min: DEFAULT_DUPLEX_SESSION_MAX_MIN,
           duplex_filler: false, duplex_ingress: true },
    stt: { engine: 'sensevoice' as 'browser' | 'sensevoice' },
    download: { aplaybox_token: '' },
    quality: {
      physics: true, pixel_ratio_cap: 2, camera_follow: false, bgm_volume: 0.5,
      background_color: '#141420', background_image: '', light_level: 1,
      stage_show: true, stage_color: '#232342', stage_glow: '#5b5bd6', stage_style: 'classic',
      stage_texture: '', stage_opacity: 1,
    },
    modules: { memory: true, scenes: true, rewrite: true, keepsake: true, tarot: true },
    hardware: {
      auto: false, tier: '', ram_gb: 0, vram_gb: 0, cores: 0,
      reason: '', fingerprint: '',
      failed: { stt: '', tts: '', memory: '' },
    },
    voices: [] as { id: string; label: string; engine?: string }[],
  }),
  getters: {
    hasLlm(): boolean {
      return !!(this.llm.api_key || '').trim() || this.llm_env || this.llm_local;
    },
  },
  actions: {
    async load() {
      const data = await api.getSettings();
      Object.assign(this.$state, data);
      const flags = data as { llm_env?: boolean; llm_local?: boolean };
      this.llm_env = !!(flags.llm_env || flags.llm_local);
      this.llm_local = this.llm_env;
      // 旧数据可能缺 engine 字段
      if (!this.tts.engine) this.tts.engine = 'edge';
      if (!this.tts.qwen_size) this.tts.qwen_size = '0.6b';
      if (!this.tts.qwen_style) this.tts.qwen_style = 'yujie';
      if (this.tts.qwen_instruct == null) this.tts.qwen_instruct = '';
      this.tts.duplex_cmd = normalizeDuplexCmd(this.tts.duplex_cmd);
      const remain = Number(this.tts.duplex_remain_sec);
      this.tts.duplex_remain_sec = Number.isFinite(remain) && remain > 0
        ? remain : DEFAULT_DUPLEX_REMAIN_SEC;
      const delayed = Number(this.tts.duplex_delayed_sec);
      this.tts.duplex_delayed_sec = delayed === 6
        ? DEFAULT_DUPLEX_DELAYED_SEC
        : Number.isFinite(delayed) && delayed >= 0
          ? delayed : DEFAULT_DUPLEX_DELAYED_SEC;
      const proactive = Number(this.tts.duplex_proactive_sec);
      this.tts.duplex_proactive_sec = proactive === 18
        ? DEFAULT_DUPLEX_PROACTIVE_SEC
        : Number.isFinite(proactive) && proactive >= 0
          ? proactive : DEFAULT_DUPLEX_PROACTIVE_SEC;
      const goodbye = Number(this.tts.duplex_goodbye_sec);
      this.tts.duplex_goodbye_sec = goodbye === 50
        ? DEFAULT_DUPLEX_GOODBYE_SEC
        : Number.isFinite(goodbye) && goodbye >= 0
          ? goodbye : DEFAULT_DUPLEX_GOODBYE_SEC;
      const sessionMax = Number(this.tts.duplex_session_max_min);
      this.tts.duplex_session_max_min = Number.isFinite(sessionMax) && sessionMax >= 0
        ? sessionMax : DEFAULT_DUPLEX_SESSION_MAX_MIN;
      if (this.tts.duplex_filler == null) this.tts.duplex_filler = false;
      if (this.tts.duplex_ingress == null) this.tts.duplex_ingress = true;
      if (!this.stt.engine) this.stt.engine = 'browser';
      const hw = (data as { hardware?: Record<string, unknown> }).hardware;
      if (hw && typeof hw === 'object') {
        const failed = (hw.failed || {}) as Record<string, string>;
        this.hardware = {
          auto: !!hw.auto,
          tier: String(hw.tier || ''),
          ram_gb: Number(hw.ram_gb || 0),
          vram_gb: Number(hw.vram_gb || 0),
          cores: Number(hw.cores || 0),
          reason: String(hw.reason || ''),
          fingerprint: String(hw.fingerprint || ''),
          failed: {
            stt: String(failed.stt || ''),
            tts: String(failed.tts || ''),
            memory: String(failed.memory || ''),
          },
        };
      }
      const mods = (data as { modules?: Record<string, boolean> }).modules;
      this.modules = {
        memory: mods?.memory !== false,
        scenes: mods?.scenes !== false,
        rewrite: mods?.rewrite !== false,
        keepsake: mods?.keepsake !== false,
        tarot: mods?.tarot !== false,
      };
      this.loaded = true;
      if (typeof this.quality.physics !== 'boolean') {
        this.quality.physics = this.quality.physics !== false && this.quality.physics !== 0;
      }
      this.applyQuality();
      this.applyTts();
      api.getVoices().then((v) => {
        this.voices = v;
        if (!v.length) return;
        const ok = v.some((x) => x.engine === this.tts.engine && x.id === this.tts.voice);
        if ((this.tts.engine === 'edge' || this.tts.engine === 'qwen' || this.tts.engine === 'cosy') && !ok) {
          this.tts.voice = '';
        }
      }).catch(() => {});
      this.maybeWarmupSpeech();
    },
    async save() {
      const data = await api.updateSettings({
        llm: this.llm, tts: this.tts, stt: this.stt,
        download: this.download, quality: this.quality, modules: this.modules,
      });
      const flags = data as { llm_env?: boolean; llm_local?: boolean };
      this.llm_env = !!(flags.llm_env || flags.llm_local);
      this.llm_local = this.llm_env;
      this.applyQuality();
      this.applyTts();
      this.maybeWarmupSpeech();
    },
    maybeWarmupSpeech() {
      // 只预热后端 ASR/TTS。前端 Silero VAD / ONNX 很占内存，等用户碰麦克风再加载
      const wantAsr = this.stt.engine === 'sensevoice';
      const wantTts = this.tts.engine === 'qwen';
      if (wantAsr && wantTts) {
        api.warmupSpeech('all', this.tts.qwen_size).catch(() => {});
      } else if (wantTts) {
        api.warmupSpeech('tts', this.tts.qwen_size).catch(() => {});
      } else if (wantAsr) {
        api.warmupSpeech('asr').catch(() => {});
      }
    },
    applyTts() {
      speechPlayer.engine = this.tts.engine as typeof speechPlayer.engine;
      speechPlayer.qwenSize = this.tts.qwen_size === '1.7b' ? '1.7b' : '0.6b';
      speechPlayer.qwenStyle = this.tts.qwen_style || '';
      speechPlayer.qwenInstruct = this.tts.qwen_instruct || '';
      speechPlayer.duplexCmd = normalizeDuplexCmd(this.tts.duplex_cmd);
      const remain = Number(this.tts.duplex_remain_sec);
      speechPlayer.duplexRemainSec = Number.isFinite(remain) && remain > 0
        ? remain : DEFAULT_DUPLEX_REMAIN_SEC;
      if (!speechPlayer.voice && this.tts.voice) speechPlayer.voice = this.tts.voice;
    },
    applyQuality() {
      stage.setQuality({
        physics: this.quality.physics,
        pixelRatioCap: this.quality.pixel_ratio_cap,
        lightLevel: this.quality.light_level,
      });
      stage.setBgmVolume(this.quality.bgm_volume ?? 0.5);
      void this.applyStageLook();
    },
    /** 情境开着时只认这场戏的背景，避免刷新先套设置再切情境。 */
    async applyStageLook() {
      try {
        const { keepsakeSession } = await import('../features/keepsake/session');
        if (keepsakeSession.bgOverride) {
          stage.setBackground(this.quality.background_color, keepsakeSession.bgOverride);
          return;
        }
      } catch { /* 证物模块未装 */ }
      if (this.modules.scenes) {
        try {
          const { sceneSession, applySceneStage } = await import('../features/scenes/session');
          if (sceneSession.current) applySceneStage(sceneSession.current);
        } catch { /* 情境未装则保持当前舞台 */ }
        return;
      }
      stage.setBackground(this.quality.background_color, this.quality.background_image);
      stage.setStagePlatform({
        show: this.quality.stage_show,
        color: this.quality.stage_color,
        glow: this.quality.stage_glow,
        style: this.quality.stage_style,
        texture: this.quality.stage_texture,
        opacity: this.quality.stage_opacity,
      });
    },
  },
});
