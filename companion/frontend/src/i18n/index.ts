import { createI18n } from 'vue-i18n';
import zhUi from '../../../locales/zh-CN/ui.json';
import enUi from '../../../locales/en/ui.json';
import jaUi from '../../../locales/ja/ui.json';
import koUi from '../../../locales/ko/ui.json';
import zhIntents from '../../../locales/zh-CN/intents.json';
import enIntents from '../../../locales/en/intents.json';
import jaIntents from '../../../locales/ja/intents.json';
import koIntents from '../../../locales/ko/intents.json';
import zhPrompts from '../../../locales/zh-CN/prompts.json';
import enPrompts from '../../../locales/en/prompts.json';
import jaPrompts from '../../../locales/ja/prompts.json';
import koPrompts from '../../../locales/ko/prompts.json';
import zhContent from '../../../locales/zh-CN/content.json';
import enContent from '../../../locales/en/content.json';
import jaContent from '../../../locales/ja/content.json';
import koContent from '../../../locales/ko/content.json';

export type ReplyLang = 'zh-CN' | 'en' | 'ja' | 'ko';

const INTS: Record<string, any> = { 'zh-CN': zhIntents, en: enIntents, ja: jaIntents, ko: koIntents };
const PROMPTS: Record<string, any> = { 'zh-CN': zhPrompts, en: enPrompts, ja: jaPrompts, ko: koPrompts };
const CONTENT: Record<string, any> = { 'zh-CN': zhContent, en: enContent, ja: jaContent, ko: koContent };

const reCache = new Map<string, RegExp>();

let reply: ReplyLang = 'zh-CN';

export const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'en',
  messages: { 'zh-CN': zhUi, en: enUi, ja: jaUi, ko: koUi },
});

export function normalizeLang(code: string | null | undefined): ReplyLang {
  const low = (code || '').trim().replace('_', '-').toLowerCase();
  if (low === 'en' || low.startsWith('en-')) return 'en';
  if (low.startsWith('ja')) return 'ja';
  if (low.startsWith('ko')) return 'ko';
  if (low === 'zh' || low.startsWith('zh-')) return 'zh-CN';
  return 'zh-CN';
}

export function bcp(lang: string = reply): string {
  if (lang === 'en') return 'en-US';
  if (lang === 'ja') return 'ja-JP';
  if (lang === 'ko') return 'ko-KR';
  return 'zh-CN';
}

export function replyLang(): ReplyLang {
  return reply;
}

export function setReplyLang(lang: string) {
  reply = normalizeLang(lang);
}

export function setUiLang(lang: string) {
  const ui = normalizeLang(lang);
  (i18n.global.locale as unknown as { value: string }).value = ui;
}

export function t(key: string, vars?: Record<string, string | number>): string {
  return String(i18n.global.t(key, vars || {}));
}

function dig(node: any, dotted: string): string {
  let cur = node;
  for (const part of dotted.split('.')) {
    if (!cur || typeof cur !== 'object' || !(part in cur)) return '';
    cur = cur[part];
  }
  return typeof cur === 'string' ? cur : '';
}

export function intentPattern(dotted: string, lang: string = reply): string {
  const pack = INTS[lang] || INTS.en || INTS['zh-CN'];
  return dig(pack, dotted) || dig(INTS['zh-CN'], dotted);
}

export function intentRe(dotted: string, lang: string = reply): RegExp {
  const key = `${lang}:${dotted}`;
  const hit = reCache.get(key);
  if (hit) return hit;
  const flags = lang === 'zh-CN' && dotted !== 'roleplay.enter' && dotted !== 'roleplay.inject' && dotted !== 'classify.dance'
    ? ''
    : 'i';
  const re = new RegExp(intentPattern(dotted, lang) || '$^', flags);
  reCache.set(key, re);
  return re;
}

export function promptPack(lang: string = reply) {
  return PROMPTS[lang] || PROMPTS.en || PROMPTS['zh-CN'];
}

export function contentPack(lang: string = reply) {
  return CONTENT[lang] || CONTENT.en || {};
}

export function featureOn(feature: 'tarot' | 'scenes', lang: string = reply): boolean {
  const pack = contentPack(lang);
  if (pack.builtin) return true;
  return !!pack[feature];
}

const QWEN: Record<string, ReplyLang> = {
  Vivian: 'zh-CN', Serena: 'zh-CN', Uncle_Fu: 'zh-CN', Dylan: 'zh-CN', Eric: 'zh-CN',
  Ryan: 'en', Aiden: 'en', Ono_Anna: 'ja', Sohee: 'ko',
};

export function voiceLang(id: string): ReplyLang | '' {
  if (QWEN[id]) return QWEN[id];
  if (id.startsWith('zh-')) return 'zh-CN';
  if (id.startsWith('en-')) return 'en';
  if (id.startsWith('ja-')) return 'ja';
  if (id.startsWith('ko-')) return 'ko';
  return '';
}

export function defaultVoice(engine: string, lang: string = reply): string {
  const l = normalizeLang(lang);
  if (engine === 'qwen') {
    if (l === 'en') return 'Serena';
    if (l === 'ja') return 'Ono_Anna';
    if (l === 'ko') return 'Sohee';
    return 'Serena';
  }
  if (l === 'en') return 'en-US-AriaNeural';
  if (l === 'ja') return 'ja-JP-NanamiNeural';
  if (l === 'ko') return 'ko-KR-SunHiNeural';
  return 'zh-CN-XiaoyiNeural';
}

export function motionTitle(name: string, stored = ''): string {
  if (reply === 'zh-CN') return stored || name;
  const map = (contentPack().motion_labels || {}) as Record<string, string>;
  if (map[name]) return map[name];
  return (name || stored).replace(/\.[^.]+$/, '');
}

export function voiceFits(voice: string, lang: string, engine = ''): boolean {
  const want = normalizeLang(lang);
  const have = voiceLang(voice);
  if (have === want) return true;
  const eng = (engine || 'qwen').toLowerCase();
  return want === 'en' && eng === 'qwen' && (voice === 'Serena' || voice === 'Vivian');
}

export function alignVoice(engine: string, voice: string, lang: string = reply): string {
  const vid = (voice || '').trim();
  const want = normalizeLang(lang);
  if (!vid) return defaultVoice(engine, want);
  if (voiceFits(vid, want, engine)) return vid;
  if (!voiceLang(vid)) return vid;
  return defaultVoice(engine, want);
}
