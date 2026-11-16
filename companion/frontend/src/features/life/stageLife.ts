import { reactive } from 'vue';
import { stage } from '../../engine/stage';
import { useSettingsStore } from '../../stores/settings';
import { isPetShell } from '../shell/mode';
import { useCharacterStore } from '../../stores/character';
import { api } from '../../api/client';
import { notifyJourney } from '../journey/session';

export const HOME_BACKGROUND = '/assets/life/room.jpg';
export const stageLife = reactive({ active: false, placed: [] as string[], preview: '', home: 'room', previewHome: '', destination: '', activity: '', activityArt: '', activityCategory: '', memoryDraft: '', vehicleStatus: '' });
let previousBackground = '';
let contextCharacter = 0;
let recentGift = '';
let recentEvent = '';
let pendingInteraction: { type: 'preview' | 'purchased' | 'offered'; item_id: string } | null = null;
function sharedActivity(kind: string) {
  const characterId = useCharacterStore().currentId || 0;
  if (characterId && useSettingsStore().modules.journey) {
    void api.journeyEvent(characterId, 'activity', kind).then(notifyJourney).catch(() => {});
  }
}
function hideStagePlatform() { stage.setStagePlatform?.({ show: false }); }
function restoreStagePlatform() { stage.setStagePlatform?.({ show: !!useSettingsStore().quality.stage_show }); }
export function setLifeCharacter(characterId: number) {
  if (contextCharacter === characterId) return;
  contextCharacter = characterId;
  recentGift = '';
  recentEvent = '';
  pendingInteraction = null;
  stageLife.memoryDraft = '';
}
export function recordLifeGift(item: string, characterId: number) { if (contextCharacter !== characterId) { leaveLifeStage(); recentEvent = ''; } contextCharacter = characterId; recentGift = item; recentEvent = 'gift'; }
export function setLifeInteraction(type: 'preview' | 'purchased' | 'offered', itemId: string) {
  pendingInteraction = { type, item_id: itemId };
}
export function lifeChatContext(characterId: number, consumeInteraction = false) {
  if (contextCharacter !== characterId) return undefined;
  const interaction = consumeInteraction ? pendingInteraction : null;
  if (consumeInteraction) pendingInteraction = null;
  return { active: stageLife.active, home: stageLife.previewHome || stageLife.home, destination: stageLife.destination, activity: stageLife.activity, placed: stageLife.placed.slice(), preview: stageLife.preview, gift: recentGift, event: recentEvent, interaction };
}
const HOMES = new Set(['room', 'rental', 'apartment', 'garden', 'villa', 'castle']);
const lifeItems = new Map<string, { category: string; art: string; kind: string; destination: string }>();
export function configureLifeItems(items: { id: string; category: string; art?: string; kind?: string; destination?: string }[]) {
  lifeItems.clear();
  for (const item of items) {
    lifeItems.set(item.id, { category: item.category, art: item.art || item.id, kind: item.kind || item.art || item.id, destination: item.destination || '' });
    if (item.category === 'home') HOMES.add(item.id);
  }
}
function homeUrl(home: string) { const art = lifeItems.get(home)?.art || home; return `/assets/life/${HOMES.has(home) ? art : 'room'}.jpg`; }
function currentUrl() { return stageLife.destination ? `/assets/life/${stageLife.destination}.jpg` : homeUrl(stageLife.previewHome || stageLife.home); }

export function enterLifeStage() {
  if (isPetShell) return false;
  const characterId = useCharacterStore().currentId || 0;
  setLifeCharacter(characterId);
  if (!stageLife.active) previousBackground = stage.getBackgroundUrl();
  stageLife.active = true;
  hideStagePlatform();
  stage.setBackground(useSettingsStore().quality.background_color, currentUrl());
  return true;
}

export function refreshLifeStage() {
  if (stageLife.active && !isPetShell) stage.setBackground(useSettingsStore().quality.background_color, currentUrl());
}

export function setLifeHome(home: string, preview = false) {
  if (!HOMES.has(home)) return;
  if (preview) stageLife.previewHome = home;
  else { if (stageLife.home !== home) recentEvent = 'home'; stageLife.home = home; stageLife.previewHome = ''; }
  if (stageLife.active && !stageLife.destination) stage.setBackground(useSettingsStore().quality.background_color, currentUrl());
}

export function visitLifeDestination(destination: string, track = true) {
  if (!['cafe', 'park', 'kitchen', 'restaurant', 'hotpot_restaurant', 'teashop', 'garage', 'coast', 'camp', 'bookstore', 'cinema', 'aquarium', 'museum', 'night_market', 'mountain'].includes(destination) || isPetShell) return false;
  recentEvent = 'visit';
  stageLife.destination = destination;
  stageLife.activity = '';
  stageLife.activityArt = '';
  stageLife.activityCategory = '';
  stageLife.previewHome = '';
  const entered = enterLifeStage();
  if (entered && track) sharedActivity(`destination:${destination}`);
  return entered;
}

export function returnLifeHome() {
  recentEvent = 'return';
  stageLife.destination = '';
  stageLife.activity = '';
  stageLife.activityArt = '';
  stageLife.activityCategory = '';
  if (stageLife.active) stage.setBackground(useSettingsStore().quality.background_color, currentUrl());
}

export async function beginTeaTime() {
  if (!visitLifeDestination('cafe', false)) return false;
  stageLife.activity = 'tea';
  stageLife.activityArt = 'tea';
  stageLife.activityCategory = 'meal';
  recentEvent = 'activity';
  sharedActivity('meal');
  return true;
}

const MEAL_LINES: Record<string, string> = {
  noodles: '面上桌了，我们一起吃吧。',
  hotpot: '火锅准备好了，想先吃什么？',
  cake: '蛋糕来了，我们一起尝尝吧。',
  home_dish: '饭菜准备好了，我们一起吃吧。',
  dessert: '甜点来了，慢慢尝。',
  coffee: '咖啡好了，我们歇一会儿吧。',
  milk_tea: '奶茶准备好了，慢慢喝。',
  fruit_tea: '果茶准备好了，一起尝尝吧。',
};

export async function beginMeal(item: string) {
  const spec = lifeItems.get(item);
  const art = spec?.category === 'meal' ? spec.art : item;
  const kind = spec?.category === 'meal' ? spec.kind : item;
  const destination = spec?.destination || (kind === 'hotpot' ? 'hotpot_restaurant' : ['coffee','milk_tea','fruit_tea'].includes(kind) ? 'teashop' : 'restaurant');
  if (!MEAL_LINES[kind] || !visitLifeDestination(destination, false)) return false;
  stageLife.activity = item;
  stageLife.activityArt = art;
  stageLife.activityCategory = 'meal';
  recentEvent = 'activity';
  sharedActivity('meal');
  return true;
}

export async function beginRide(item: string) {
  const spec = lifeItems.get(item);
  const art = spec?.category === 'vehicle' ? spec.art : item;
  const kind = spec?.category === 'vehicle' ? spec.kind : item;
  if (!['bicycle', 'scooter', 'car', 'fuel_car', 'camper'].includes(kind) || !visitLifeDestination(spec?.destination || (kind === 'camper' ? 'camp' : 'park'), false)) return false;
  stageLife.activity = item;
  stageLife.activityArt = art;
  stageLife.activityCategory = 'vehicle';
  recentEvent = 'activity';
  sharedActivity('vehicle');
  return true;
}

export function endLifeActivity() { stageLife.activity = ''; stageLife.activityArt = ''; stageLife.activityCategory = ''; recentEvent = 'end'; }

export function endLifePreview() {
  stageLife.preview = '';
  stageLife.previewHome = '';
  if (stageLife.active) stage.setBackground(useSettingsStore().quality.background_color, currentUrl());
}

export function leaveLifeStage() {
  recentEvent = 'leave';
  const shouldRestore = stageLife.active && stage.getBackgroundUrl() === currentUrl();
  const wasActive = stageLife.active;
  stageLife.active = false;
  stageLife.preview = '';
  stageLife.previewHome = '';
  stageLife.destination = '';
  stageLife.activity = '';
  stageLife.activityArt = '';
  stageLife.activityCategory = '';
  if (wasActive) restoreStagePlatform();
  if (shouldRestore) stage.setBackground(useSettingsStore().quality.background_color, previousBackground);
}

// A different feature explicitly took the stage. Do not restore over it later.
window.addEventListener('xiaokeai:stage-background', (event) => {
  if (stageLife.active && (event as CustomEvent<string>).detail !== currentUrl()) {
    restoreStagePlatform();
    stageLife.active = false;
    stageLife.preview = '';
    stageLife.previewHome = '';
    stageLife.destination = '';
    stageLife.activity = '';
    stageLife.activityArt = '';
    stageLife.activityCategory = '';
  }
});
