import { defineStore } from 'pinia';
import { api } from '../api/client';
import { defaultLive, normalizeLive } from '../features/live/config';
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
import { alignVoice, defaultVoice, normalizeLang, setReplyLang, setUiLang } from '../i18n';

import { inferLlmPreset, LLM_PRESETS } from '../features/settings/llmPresets';

const defaultLlm = {
  base_url: 'https://ark.cn-beijing.volces.com/api/v3', api_key: '',
  model: 'doubao-seed-character-260628', temperature: 0.85, top_p: 1.0,
  max_tokens: 0, thinking: 'off',
  preset: '', harness_model: '', harness_base_url: '', harness_api_key: '',
};

let stageLookRevision = 0;

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    loaded: false,
    llm_env: false,
    llm_local: false,
    llm: { ...defaultLlm },
    llm_presets: {} as Partial<Record<string, typeof defaultLlm>>,
    tts: { engine: 'qwen' as 'cosy' | 'edge' | 'qwen' | 'tera' | 'volc' | 'openai' | 'eleven' | 'gemini' | 'mimo' | 'browser' | 'off',
           voice: 'Serena', rate: '+0%', qwen_size: '0.6b' as '0.6b' | '1.7b',
           qwen_style: 'yujie' as string, qwen_instruct: '',
           duplex_cmd: 'interrupt_or_queue' as DuplexCmd,
           duplex_remain_sec: DEFAULT_DUPLEX_REMAIN_SEC,
           duplex_delayed_sec: DEFAULT_DUPLEX_DELAYED_SEC,
           duplex_proactive_sec: DEFAULT_DUPLEX_PROACTIVE_SEC,
           duplex_goodbye_sec: DEFAULT_DUPLEX_GOODBYE_SEC,
           duplex_session_max_min: DEFAULT_DUPLEX_SESSION_MAX_MIN,
           duplex_filler: false, duplex_ingress: true,
           voice_by_engine: {} as Record<string, Record<string, string>>,
           tavern_cast: {} as Record<string, Record<string, { engine: string; voice: string }>> },
    stt: { engine: 'sensevoice' as 'browser' | 'sensevoice' | 'ali' | 'volc' | 'openai' | 'eleven' | 'gemini' },
    omni: {
      chat_url: 'https://api.modelbest.cn/v1',
      realtime_host: 'https://minicpmo45.modelbest.cn',
      api_key: '',
      model: 'MiniCPM-O-4.5-9B',
    },
    omni_env: false,
    locale: {
      ui: 'zh-CN' as 'zh-CN' | 'en' | 'ja' | 'ko' | 'ru',
      reply: 'zh-CN' as 'zh-CN' | 'en' | 'ja' | 'ko' | 'ru',
      reply_mode: 'fixed' as 'fixed' | 'follow',
    },
    locale_set: false,
    download: { aplaybox_token: '' },
    quality: {
      physics: false, pbr: true, pixel_ratio_cap: 2, camera_follow: false, bgm_volume: 0.5,
      background_color: '#141420', background_image: '', light_level: 1,
      stage_show: true, stage_color: '#232342', stage_glow: '#5b5bd6', stage_style: 'classic',
      stage_texture: '', stage_opacity: 1, live2d_enabled: false,
    },
    modules: { memory: true, scenes: true, rewrite: true, keepsake: true, tarot: true, tavern: true, codewatch: true, touch: true, harness: true, glance: false, live_douyin: false, live: false, play: true, journey: true },
    live: defaultLive(),
    vision: { provider: 'minicpm' as 'minicpm' | 'openai', generator: 'chat' as 'chat' | 'minicpm', base_url: '', api_key: '', model: '' },
    memory: { embedder: 'auto' as 'auto' | 'local' | 'doubao' | 'qwen' | 'openai' | 'gemini' },
    user_persona: { enabled: false, name: '', description: '' },
    hardware: {
      auto: false, tier: '', ram_gb: 0, vram_gb: 0, cores: 0,
      reason: '', fingerprint: '',
      failed: { stt: '', tts: '', memory: '' },
    },
    voices: [] as { id: string; label: string; engine?: string; lang?: string }[],
    content: {
      packed: false,
      path: '',
      ok: false,
      found: {} as Record<string, boolean>,
    },
  }),
  getters: {
    llmPreset(): string {
      return this.llm.preset || inferLlmPreset(this.llm.base_url, this.llm.model);
    },
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
      this.llm = { ...defaultLlm, ...data.llm };
      this.llm.preset = this.llmPreset;
      this.llm_presets = data.llm_presets || {};
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
      this.tts.voice_by_engine ||= {
        [this.tts.engine]: (data.tts as { voice_by_lang?: Record<string, string> })?.voice_by_lang || {},
      };
      if (!this.tts.tavern_cast || typeof this.tts.tavern_cast !== 'object') {
        this.tts.tavern_cast = {};
      }
      if (!this.stt.engine) this.stt.engine = 'browser';
      const omni = (data as { omni?: Record<string, unknown>; omni_env?: boolean }).omni;
      this.omni = {
        chat_url: String(omni?.chat_url || 'https://api.modelbest.cn/v1'),
        realtime_host: String(omni?.realtime_host || 'https://minicpmo45.modelbest.cn'),
        api_key: String(omni?.api_key || ''),
        model: String(omni?.model || 'MiniCPM-O-4.5-9B'),
      };
      this.omni_env = !!((data as { omni_env?: boolean }).omni_env);
      const loc = (data as { locale?: { ui?: string; reply?: string; reply_mode?: string }; locale_set?: boolean });
      this.locale_set = !!loc.locale_set;
      const ui = normalizeLang(loc.locale?.ui || 'zh-CN');
      const reply = normalizeLang(loc.locale?.reply || 'zh-CN');
      this.locale = {
        ui, reply,
        reply_mode: loc.locale?.reply_mode === 'follow' ? 'follow' : 'fixed',
      };
      if (!this.locale_set && typeof navigator !== 'undefined') {
        const nav = navigator.language.toLowerCase();
        const os = nav.startsWith('zh') ? 'zh-CN' : nav.startsWith('ru') ? 'ru' : nav.startsWith('ko') ? 'ko' : nav.startsWith('ja') ? 'ja' : 'en';
        this.locale = { ui: os, reply: os, reply_mode: 'fixed' };
        this.tts.voice = alignVoice(this.tts.engine, this.tts.voice, os);
      }
      setUiLang(this.locale.ui);
      setReplyLang(this.locale.reply);
      window.companionDesktop?.setTrayLocale?.(this.locale.ui);
      const alignedNow = alignVoice(this.tts.engine, this.tts.voice, this.locale.reply);
      if (alignedNow && alignedNow !== this.tts.voice && this.locale_set) {
        this.tts.voice = alignedNow;
        void this.save();
      }
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
        tavern: mods?.tavern !== false,
        codewatch: mods?.codewatch !== false,
        touch: mods?.touch !== false,
        harness: mods?.harness === true,
        play: mods?.play !== false,
        glance: mods?.glance === true,
        live_douyin: mods?.live_douyin === true,
        live: mods?.live === true,
        journey: mods?.journey !== false,
      };
      this.live = normalizeLive((data as { live?: unknown }).live);
      const vision = (data as { vision?: { provider?: string; generator?: string; base_url?: string; api_key?: string; model?: string } }).vision;
      this.vision = {
        provider: vision?.provider === 'openai' ? 'openai' : 'minicpm',
        generator: vision?.generator === 'minicpm' ? 'minicpm' : 'chat',
        base_url: String(vision?.base_url || ''),
        api_key: String(vision?.api_key || ''),
        model: String(vision?.model || ''),
      };
      const mem = (data as { memory?: { embedder?: string } }).memory;
      const emb = String(mem?.embedder || 'auto');
      this.memory = {
        embedder: (emb === 'local' || emb === 'doubao' || emb === 'qwen' || emb === 'openai' || emb === 'gemini' ? emb : 'auto'),
      };
      const up = (data as { user_persona?: { enabled?: boolean; name?: string; description?: string } }).user_persona;
      this.user_persona = {
        enabled: !!up?.enabled,
        name: String(up?.name || ''),
        description: String(up?.description || ''),
      };
      const content = (data as { content?: Record<string, unknown> }).content;
      if (content && typeof content === 'object') {
        this.content = {
          packed: !!content.packed,
          path: String(content.path || ''),
          ok: !!content.ok,
          found: (content.found || {}) as Record<string, boolean>,
        };
      }
      this.loaded = true;
      if (typeof this.quality.physics !== 'boolean') {
        this.quality.physics = false;
      }
      this.quality.pbr ??= true;
      this.applyQuality();
      this.applyTts();
      api.getVoices().then((voices) => { this.voices = voices; }).catch(() => {});
      this.maybeWarmupSpeech();
    },
    selectLlmPreset(preset: string) {
      const previous = this.llmPreset;
      if (preset === previous) return;
      if (preset !== 'custom' && !Object.prototype.hasOwnProperty.call(LLM_PRESETS, preset)) return;
      this.llm_presets[previous] = { ...this.llm, preset: previous };
      const defaults = LLM_PRESETS[preset];
      const local = ['ollama', 'vllm', 'sglang', 'player2'].includes(preset);
      this.llm = {
        ...defaultLlm,
        base_url: defaults?.base ?? '',
        model: defaults?.model ?? '',
        api_key: local ? 'ollama' : '',
        ...this.llm_presets[preset],
        preset,
      };
    },
    selectTtsEngine(engine: typeof this.tts.engine) {
      if (engine === this.tts.engine) return;
      this.noteVoice();
      this.tts.engine = engine;
      this.restoreVoice();
    },
    noteVoice() {
      const { engine, voice } = this.tts;
      if (!voice) return;
      const lang = this.locale.reply;
      this.tts.voice = alignVoice(engine, voice, lang);
      this.tts.voice_by_engine[engine] = {
        ...this.tts.voice_by_engine[engine],
        [lang]: this.tts.voice,
      };
    },
    restoreVoice() {
      const { engine } = this.tts;
      const lang = this.locale.reply;
      this.tts.voice = this.tts.voice_by_engine[engine]?.[lang]
        ?? (engine === 'cosy' || engine === 'off' || engine === 'browser' ? '' : defaultVoice(engine, lang));
    },
    async save() {
      this.noteVoice();
      const data = await api.updateSettings({
        llm: { ...this.llm, preset: this.llmPreset }, llm_presets: this.llm_presets, tts: this.tts, stt: this.stt, omni: this.omni, vision: this.vision,
        locale: this.locale,
        download: this.download, quality: this.quality, modules: this.modules,
        live: this.live,
        memory: this.memory,
        user_persona: this.user_persona,
      });
      const flags = data as { llm_env?: boolean; llm_local?: boolean; omni_env?: boolean };
      this.llm_env = !!(flags.llm_env || flags.llm_local);
      this.llm_local = this.llm_env;
      this.omni_env = !!flags.omni_env;
      this.applyQuality();
      this.applyTts();
      this.maybeWarmupSpeech();
    },
    async setLocale(patch: Partial<{ ui: 'zh-CN' | 'en' | 'ja' | 'ko' | 'ru'; reply: 'zh-CN' | 'en' | 'ja' | 'ko' | 'ru'; reply_mode: 'fixed' | 'follow' }>) {
      const prevReply = this.locale.reply;
      this.noteVoice();
      this.locale = { ...this.locale, ...patch };
      setUiLang(this.locale.ui);
      setReplyLang(this.locale.reply);
      window.companionDesktop?.setTrayLocale?.(this.locale.ui);
      if (this.locale.reply !== prevReply) this.restoreVoice();
      await this.save();
      const scenes = await import('../features/scenes/session');
      scenes.reloadSceneLocale();
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
        pbr: this.quality.pbr,
        pixelRatioCap: this.quality.pixel_ratio_cap,
        lightLevel: this.quality.light_level,
      });
      stage.setBgmVolume(this.quality.bgm_volume ?? 0.5);
      void this.applyStageLook();
    },
    /** 情境开着时只认这场戏的背景，避免刷新先套设置再切情境。 */
    async applyStageLook() {
      const revision = ++stageLookRevision;
      const q = this.quality;
      const applyPlatform = () => stage.setStagePlatform({
        show: q.stage_show,
        color: q.stage_color,
        glow: q.stage_glow,
        style: q.stage_style,
        texture: q.stage_texture,
        opacity: q.stage_opacity,
      });
      const { stageLife, refreshLifeStage } = await import('../features/life/stageLife');
      if (revision !== stageLookRevision) return;
      if (stageLife.active) { applyPlatform(); refreshLifeStage(); return; }
      try {
        const { keepsakeSession } = await import('../features/keepsake/session');
        if (revision !== stageLookRevision) return;
        if (stageLife.active) { applyPlatform(); refreshLifeStage(); return; }
        if (keepsakeSession.bgOverride) {
          applyPlatform();
          stage.setBackground(q.background_color, keepsakeSession.bgOverride);
          return;
        }
      } catch { /* 证物模块未装 */ }
      if (this.modules.scenes) {
        try {
          const { sceneSession, applySceneStage } = await import('../features/scenes/session');
          if (revision !== stageLookRevision) return;
          if (stageLife.active) { applyPlatform(); refreshLifeStage(); return; }
          if (this.modules.scenes && sceneSession.current) {
            applySceneStage(sceneSession.current);
            return;
          }
        } catch { /* 情境不可用时使用舞台设置 */ }
      }
      if (revision !== stageLookRevision) return;
      applyPlatform();
      if (stageLife.active) { refreshLifeStage(); return; }
      stage.setBackground(q.background_color, q.background_image);
    },
    async applyContent(path: string) {
      const r = await api.setContent(path);
      if (!r.ok) {
        return r;
      }
      this.content = {
        packed: !!r.packed,
        path: String(r.path || path),
        ok: !!(r.ok && !r.restart),
        found: r.found || {},
      };
      return r;
    },
  },
});
