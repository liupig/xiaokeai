<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { api, type TavernCard, type TavernNote, type TavernState } from '../../api/client';
import { stage } from '../../engine/stage';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';
import { caster } from '../performance/caster';
import { t } from '../../i18n';
import { CARD_DECKS, CARD_STYLES, DECK_FACES, loadCardDeck, loadCardStyle, saveCardDeck, saveCardStyle, setFaceNames } from './cards';
import { artUrl, packOf } from './copy';
import { mountTavern, refreshCardArt, syncTavern, unmountTavern } from './plugin';
import { coins, refreshCoinsSoon } from '../coins/session';
import { closeTavern } from './session';
import { applause, cock, cylinder, dread, killshot, pick, primeApplause, primeCollapse, primeShot, pulse, relieved, slide, stopDread, turn, unlock } from './sound';
import { stopTalk, talk } from './voice';

const characters = useCharacterStore();
const chat = useChatStore();
const settings = useSettingsStore();
const copy = computed(() => packOf(settings.locale.ui));

const state = ref<TavernState | null>(null);
const selected = ref<string[]>([]);
const error = ref('');
const busy = ref(false);
const shock = ref(false);
const muzzle = ref(false);
const triumph = ref<{ id: string; rank: number } | null>(null);
let triumphQueue: { id: string; rank: number }[] = [];
let triumphTimer = 0;
const boardOpen = ref(false);
const coinNote = ref('');
const cyl = ref(0);
const log = ref<{ seq: number; verb: string; text: string }[]>([]);
const hearing = ref(false);
const spotlight = ref('');
const spotVerb = ref('');
let spinTimer = 0;
let paidSeq = 0;
let saidNow: Promise<void> = Promise.resolve();
let pace = 0;

const RITE_FLIP = 2600;
const RITE_GUN = 4800;
const RITE_END = 3400;
const LINE_HOLD = 2600;

let timers: number[] = [];
let epoch = 0;
const riteBeat = ref<'flip' | 'gun' | 'end' | ''>('');
const hold = ref<{ id: string; cards: number; pulls: number; hand: TavernCard[] } | null>(null);

const lobby = computed(() => !state.value || state.value.phase === 'idle');
const seatOf = computed(() => {
  const map: Record<string, { alive: boolean; cards: number; pulls: number; out?: boolean }> = {};
  for (const seat of state.value?.seats || []) map[seat.id] = seat;
  return map;
});
const canAct = computed(() => state.value?.phase === 'act' && state.value.turn === 'you' && !!state.value.you?.alive && !busy.value && !hearing.value);
const canCall = computed(() => canAct.value && !!state.value?.pile);
const canName = computed(() => state.value?.phase === 'name' && state.value.turn === 'you' && !!state.value.you?.alive && !busy.value && !hearing.value);
const tableEmpty = computed(() => {
  const seats = (state.value?.seats || []).filter((seat) => seat.alive);
  const phase = state.value?.phase;
  return seats.length > 1 && seats.every((seat) => !seat.cards) && (phase === 'act' || phase === 'name');
});
const deckId = ref(loadCardDeck());
const styleId = ref(loadCardStyle());
const suits = computed(() => (state.value?.faces?.length ? state.value.faces : DECK_FACES[deckId.value]));
const hint = computed(() => {
  const s = state.value;
  if (!s) return '';
  if (tableEmpty.value) return copy.value.spentHint;
  if (s.phase === 'name') return s.turn === 'you' ? copy.value.nameHint : copy.value.think(nameOf(s.turn || ''), true);
  if (s.phase !== 'act') return '';
  if (s.turn === 'you') return s.pile ? copy.value.yourTurn : copy.value.first;
  return copy.value.think(nameOf(s.turn || ''), false);
});
const riteWords = computed(() => {
  const show = state.value?.show;
  const c = copy.value;
  if (!show || show.kind !== 'reveal') return log.value[log.value.length - 1]?.text || '';
  if (riteBeat.value === 'gun') return c.sayGun(nameOf(show.shooter || ''), (hold.value?.pulls || 0) + 1);
  if (riteBeat.value === 'end') return show.hit ? c.sayShot(nameOf(show.shooter || '')) : c.sayClick(nameOf(show.shooter || ''));
  return c.sayReveal({
    caller: nameOf(show.caller || ''),
    actor: nameOf(show.actor || ''),
    cards: (show.cards || []).map(faceName).join(c.comma),
    honest: !!show.honest,
    shooter: nameOf(show.shooter || ''),
    hit: !!show.hit,
  });
});
const riteReady = computed(() => state.value?.show?.kind !== 'reveal' || riteBeat.value === 'end');
const focusId = computed(() => {
  const s = state.value;
  if (!s || s.phase === 'idle' || s.phase === 'over') return '';
  if (s.phase === 'show' && s.show?.kind === 'reveal') {
    return riteBeat.value === 'flip' ? (s.show.caller || '') : (s.show.shooter || '');
  }
  if (spotlight.value) return spotlight.value;
  return s.turn || '';
});
const focusText = computed(() => {
  const s = state.value;
  if (s?.phase === 'show' && s.show?.kind === 'reveal') {
    return riteBeat.value === 'flip' ? copy.value.focusCall : copy.value.focusRite;
  }
  if (spotVerb.value && spotlight.value) return spotVerb.value;
  if (s?.phase === 'name') return copy.value.focusName;
  return copy.value.focusPlay;
});
const shownLog = computed(() => log.value.slice(-4));
const farewell = computed(() => {
  const show = state.value?.show;
  if (riteBeat.value !== 'end' || !show?.hit) return '';
  return show.shooter || '';
});

function pumpTriumph() {
  if (triumph.value || !triumphQueue.length) return;
  const next = triumphQueue.shift();
  if (!next) return;
  triumph.value = next;
  applause();
  triumphTimer = window.setTimeout(() => {
    triumph.value = null;
    pumpTriumph();
  }, 4800);
}
function celebrate(rows: { id: string; rank: number }[]) {
  const seen = new Set(triumphQueue.map((row) => row.id));
  if (triumph.value) seen.add(triumph.value.id);
  for (const row of rows) {
    if (!row.id || seen.has(row.id)) continue;
    triumphQueue.push(row);
    seen.add(row.id);
  }
  pumpTriumph();
}

function suitOf(id: string) {
  return (id || '').split(':')[0];
}
function faceName(id: string) {
  const suit = suitOf(id);
  const key = `tavern.face.${suit}`;
  const named = t(key);
  if (named && named !== key) return named;
  return copy.value.face[suit]?.name || suit;
}
function nameOf(id: string) {
  if (id === 'host') return copy.value.host;
  if (id === 'her') return state.value?.her_name || copy.value.seat.her;
  return copy.value.seat[id] || id;
}
function say(note: TavernNote) {
  const c = copy.value;
  if (note.t === 'play') return c.sayPlay(nameOf(note.who || ''), note.n || 0);
  if (note.t === 'deal') return c.sayDeal(faceName(note.face || ''), nameOf(note.who || ''));
  if (note.t === 'rite') return c.sayRite(nameOf(note.who || ''));
  if (note.t === 'name') return c.sayName(nameOf(note.who || ''), faceName(note.face || ''));
  if (note.t === 'clear') return c.sayClear(nameOf(note.who || ''));
  if (note.t === 'win') return c.sayWin(nameOf(note.who || ''));
  if (note.t === 'reveal') {
    return c.sayReveal({
      caller: nameOf(note.caller || ''),
      actor: nameOf(note.actor || ''),
      cards: (note.cards || []).map(faceName).join(c.comma),
      honest: !!note.honest,
      shooter: nameOf(note.shooter || ''),
      hit: !!note.hit,
    });
  }
  return '';
}

function clearTimers() {
  for (const id of timers) window.clearTimeout(id);
  timers = [];
}
function later(ms: number, fn: () => void) {
  const mine = epoch;
  const id = window.setTimeout(() => {
    if (mine !== epoch) return;
    fn();
  }, ms);
  timers.push(id);
}
function stopSpin() {
  if (spinTimer) window.clearInterval(spinTimer);
  spinTimer = 0;
}
function stop() {
  epoch += 1;
  pace += 1;
  clearTimers();
  stopSpin();
  riteBeat.value = '';
  hold.value = null;
  muzzle.value = false;
  hearing.value = false;
  spotlight.value = '';
  spotVerb.value = '';
  pulse(false);
  stopDread();
  stopTalk();
}
function sleep(ms: number) {
  return new Promise<void>((resolve) => { window.setTimeout(resolve, ms); });
}

function voiceFor(id: string) {
  const engine = settings.tts.engine;
  const cast: Record<string, Record<string, string>> = {
    edge: {
      you: 'zh-CN-YunxiNeural',
      qin: 'zh-CN-XiaoxiaoNeural',
      bar: 'zh-CN-YunjianNeural',
      her: 'zh-CN-XiaoyiNeural',
      host: 'zh-CN-YunyangNeural',
    },
    qwen: { you: 'Dylan', qin: 'Vivian', bar: 'Eric', her: 'Serena', host: 'Uncle_Fu' },
  };
  if (id === 'host') return cast[engine]?.host || cast.edge.host;
  if (id === 'her') {
    const own = (characters.current?.voice || '').trim();
    const edgeOk = engine === 'edge' && own.includes('Neural');
    const qwenOk = engine === 'qwen' && ['Vivian', 'Serena', 'Uncle_Fu', 'Dylan', 'Eric'].includes(own);
    if (edgeOk || qwenOk) return own;
  }
  return cast[engine]?.[id] || settings.tts.voice || '';
}

function speakerOf(note: TavernNote) {
  if (note.t === 'deal') return 'host';
  if (note.t === 'reveal') return note.caller || '';
  return note.who || '';
}

function localLine(note: TavernNote) {
  const c = copy.value;
  if (note.t === 'play') {
    const n = note.n || 1;
    const face = faceName(state.value?.table || '');
    if (note.follow === false && (settings.locale.ui || '').startsWith('zh')) {
      return `我先出。${['', '一', '两', '三'][n] || n}张${face}。`;
    }
    return c.linePlay(n, face);
  }
  if (note.t === 'name') return c.lineName(faceName(note.face || ''));
  if (note.t === 'deal') return c.lineHost(faceName(note.face || ''), nameOf(note.who || ''));
  if (note.t === 'reveal') return c.lineCall;
  if (note.t === 'clear') return c.lineClear;
  return '';
}

function verbOf(note: TavernNote) {
  const v = copy.value.verb;
  if (note.t === 'play') return note.follow === false ? v.play : v.follow;
  if (note.t === 'reveal') return v.call;
  if (note.t === 'name') return v.name;
  if (note.t === 'deal') return note.dealt === false ? v.keep : v.deal;
  if (note.t === 'clear') return v.clear;
  return '';
}

function spokenLine(s: TavernState) {
  const note = s.note;
  if (!note) return '';
  const c = copy.value;
  if (note.t === 'deal') {
    const ids = note.seated?.length
      ? note.seated
      : (s.seats || []).filter((seat) => seat.alive).map((seat) => seat.id);
    if (ids.length && (note.dealt === false || ids.length < (s.seats || []).length)) {
      const names = ids.map((id) => nameOf(id)).join(c.comma);
      const face = faceName(note.face || s.table || '');
      const who = nameOf(note.who || '');
      return note.dealt === false ? c.lineKeep(names, face, who) : c.lineStill(names, face, who);
    }
  }
  let line = (note.line || '').trim() || localLine(note);
  if (!line) return '';
  const zh = (settings.locale.ui || '').startsWith('zh');
  if (zh && note.t === 'play' && note.follow === false && /^跟/.test(line)) {
    line = `我先出。${line.replace(/^跟[，。,\s]*/, '')}`;
  }
  if (zh && note.t === 'play' && note.follow !== false && !line.includes('跟')) line = `我跟。${line}`;
  if (zh && note.t === 'reveal' && !/[揭穿]/.test(line)) line = `揭穿。${line}`;
  return line;
}

function speak(who: string, text: string) {
  const line = (text || '').trim();
  if (!line) return Promise.resolve();
  unlock();
  if (who === 'her') caster.onSpeakSentence(line);
  return talk(line, who, voiceFor(who), settings.tts.engine);
}

watch(riteBeat, (beat) => {
  const show = state.value?.show;
  const shooter = show?.shooter || '';
  stopSpin();
  if (beat === 'flip') turn();
  else if (beat === 'gun') {
    cyl.value = 0;
    pulse(true);
    dread();
    cock();
    void primeShot();
    spinTimer = window.setInterval(() => {
      cyl.value += 60;
      cylinder();
    }, 720);
    speak(shooter, copy.value.lineGun((hold.value?.pulls || 0) + 1));
  } else if (beat === 'end') {
    if (show?.kind === 'reveal' && show.hit) {
      stopTalk();
      killshot();
      muzzle.value = true;
      window.setTimeout(() => { muzzle.value = false; }, 680);
      window.setTimeout(() => { speak(shooter, copy.value.lineShot); }, 1100);
    } else if (show?.kind === 'reveal') {
      relieved();
      speak(shooter, copy.value.lineClick);
    }
  } else {
    pulse(false);
    stopDread();
  }
  pushBoard();
});

function armShow(s: TavernState) {
  const mine = ++pace;
  const pending = saidNow;
  if (s.show?.kind !== 'reveal') {
    riteBeat.value = 'end';
    void (async () => {
      await Promise.race([Promise.all([pending, sleep(2200)]), sleep(8000)]);
      if (mine !== pace) return;
      if (state.value?.phase === 'show') void send('ack');
    })();
    return;
  }
  riteBeat.value = 'flip';
  later(RITE_FLIP, () => { riteBeat.value = 'gun'; });
  const endHold = s.show?.hit ? 5600 : RITE_END;
  later(RITE_FLIP + RITE_GUN, () => {
    riteBeat.value = 'end';
    hold.value = null;
    pushBoard();
    if (state.value?.show?.hit) {
      shock.value = true;
      window.setTimeout(() => { shock.value = false; }, 1400);
    }
  });
  later(RITE_FLIP + RITE_GUN + endHold, () => {
    if (state.value?.phase === 'show') void send('ack');
  });
}

function schedule(s: TavernState) {
  clearTimers();
  hearing.value = false;
  if (s.phase === 'show') {
    armShow(s);
    return;
  }
  riteBeat.value = '';
  const mine = ++pace;
  const pending = saidNow;
  const aliveSeats = (s.seats || []).filter((seat) => seat.alive);
  const tableSpent = aliveSeats.length > 1 && aliveSeats.every((seat) => !seat.cards);
  const ai = (s.phase === 'act' || s.phase === 'name') && !!s.turn && s.turn !== 'you';
  void (async () => {
    const hold = spotlight.value ? LINE_HOLD : 400;
    hearing.value = !!spotlight.value;
    await Promise.race([Promise.all([pending, sleep(hold)]), sleep(9000)]);
    if (mine !== pace) return;
    hearing.value = false;
    spotlight.value = '';
    spotVerb.value = '';
    pushBoard();
    if (tableSpent || !ai) return;
    const now = state.value;
    const still = (now?.phase === 'act' || now?.phase === 'name') && !!now.turn && now.turn !== 'you';
    if (still) void send('step');
  })();
}

function pushBoard() {
  const s = state.value;
  syncTavern({
    phase: s?.phase || 'idle',
    truth: s?.table || '',
    hand: hold.value?.id === 'you' ? hold.value.hand : (s?.you?.hand || []),
    selected: selected.value,
    seats: (s?.seats || []).map((seat) => ({ id: seat.id, alive: alive(seat.id), cards: shownCards(seat.id) })),
    pile: s?.pile?.n || 0,
    pileFrom: s?.pile?.actor || '',
    reveal: s?.phase === 'show' && s.show?.kind === 'reveal' ? (s.show.cards || []) : [],
    focus: focusId.value,
    faces: suits.value,
  });
}

function apply(s: TavernState) {
  const hadTable = !!state.value && state.value.phase !== 'idle';
  const prevOut = new Set((state.value?.seats || []).filter((seat) => seat.out).map((seat) => seat.id));
  if (s.phase === 'idle') {
    log.value = [];
    triumphQueue = [];
    triumph.value = null;
    if (triumphTimer) window.clearTimeout(triumphTimer);
  }
  if (s.phase === 'show' && s.show?.kind === 'reveal') {
    const id = s.show.shooter || '';
    const prev = seatOf.value[id];
    const nowPulls = (s.seats || []).find((seat) => seat.id === id)?.pulls || 0;
    hold.value = {
      id,
      cards: prev?.cards ?? 0,
      pulls: prev?.pulls ?? Math.max(0, nowPulls - 1),
      hand: id === 'you' ? (state.value?.you?.hand || []).map((card) => ({ ...card })) : [],
    };
  } else {
    hold.value = null;
  }
  state.value = s;
  if (hadTable) {
    const born = (s.seats || [])
      .filter((seat) => seat.alive && seat.out && !prevOut.has(seat.id))
      .map((seat) => ({ id: seat.id, rank: seat.finish || 1 }))
      .sort((a, b) => a.rank - b.rank);
    if (born.length) celebrate(born);
  }
  const ids = new Set((s.you?.hand || []).map((card) => card.id));
  selected.value = selected.value.filter((id) => ids.has(id));
  saidNow = Promise.resolve();
  if (s.note?.seq && !log.value.some((row) => row.seq === s.note!.seq)) {
    const said = spokenLine(s);
    const who = nameOf(speakerOf(s.note));
    const verb = verbOf(s.note);
    const text = said ? `${who}：${said}` : say(s.note);
    if (s.note.t === 'play') slide();
    if (said) {
      spotlight.value = speakerOf(s.note);
      spotVerb.value = verb;
      saidNow = speak(speakerOf(s.note), said);
    } else {
      spotlight.value = '';
      spotVerb.value = '';
    }
    if (text) log.value = [...log.value, { seq: s.note.seq, verb, text }].slice(-8);
    if (s.note.t === 'win' && s.note.seq !== paidSeq) {
      paidSeq = s.note.seq;
      if (typeof s.balance_milli === 'number') coins.balanceMilli = s.balance_milli;
      if (s.coin_delta) {
        coinNote.value = copy.value.coinLine(s.coin_delta);
        refreshCoinsSoon();
      }
    }
  }
  error.value = '';
  pushBoard();
  schedule(s);
}

async function send(kind: 'refresh' | 'start' | 'play' | 'call' | 'ack' | 'step' | 'name' | 'next' | 'end', face = '') {
  const mine = epoch;
  const cid = characters.currentId || 0;
  busy.value = true;
  try {
    let next: TavernState;
    if (kind === 'refresh') next = await api.tavernState(cid);
    else if (kind === 'start') next = await api.tavernStart(cid, characters.current?.name || copy.value.seat.her, deckId.value);
    else if (kind === 'name') next = await api.tavernName(cid, face);
    else if (kind === 'play') next = await api.tavernPlay(cid, selected.value);
    else if (kind === 'call') next = await api.tavernCall(cid);
    else if (kind === 'ack') next = await api.tavernAck(cid);
    else if (kind === 'next') next = await api.tavernNext(cid);
    else if (kind === 'end') next = await api.tavernEnd(cid);
    else next = await api.tavernStep(cid);
    if (mine !== epoch) return;
    apply(next);
  } catch (err) {
    if (mine !== epoch) return;
    const code = err instanceof Error ? err.message : 'wait';
    error.value = copy.value.err[code] || code;
  } finally {
    if (mine === epoch) busy.value = false;
  }
}

function enter() {
  unlock();
  log.value = [];
  selected.value = [];
  coinNote.value = '';
  paidSeq = 0;
  stop();
  void send('start');
}

async function pickWho(id: number) {
  if (!id || id === characters.currentId || busy.value) return;
  busy.value = true;
  try {
    await characters.switchTo(id);
  } finally {
    busy.value = false;
  }
}

function endNight() {
  stop();
  log.value = [];
  selected.value = [];
  void send('end');
}
function onName(face: string) {
  unlock();
  stop();
  void send('name', face);
}
function onPlay() {
  if (!selected.value.length) return;
  unlock();
  stop();
  void send('play');
}
function onCall() {
  unlock();
  stop();
  void send('call');
}
function cont() {
  stop();
  void send('ack');
}
function onNext() {
  unlock();
  stop();
  void send('next');
}
function toggle(id: string) {
  if (!canAct.value) return;
  unlock();
  const has = selected.value.includes(id);
  if (has) selected.value = selected.value.filter((card) => card !== id);
  else if (selected.value.length < 3) {
    selected.value = [...selected.value, id];
    pick();
  }
  pushBoard();
}
function onKey(ev: KeyboardEvent) {
  if (ev.key !== 'Escape') return;
  closeTavern();
}
function pulls(id: string) {
  if (hold.value?.id === id) return hold.value.pulls;
  if (id === 'you') return state.value?.you?.pulls || 0;
  return seatOf.value[id]?.pulls || 0;
}
function alive(id: string) {
  if (hold.value?.id === id) return true;
  return seatOf.value[id]?.alive === true;
}
function shownCards(id: string) {
  if (!alive(id)) return 0;
  if (hold.value?.id === id) return hold.value.cards;
  return seatOf.value[id]?.cards || 0;
}
function seatMark(id: string) {
  if (!alive(id)) return copy.value.dead;
  if (seatOf.value[id]?.out) return copy.value.aside;
  if (!shownCards(id) && (state.value?.phase === 'act' || state.value?.phase === 'name')) return copy.value.bye;
  return String(shownCards(id));
}
function chamberClass(n: number) {
  const show = state.value?.show;
  if (!show || show.kind !== 'reveal') return '';
  const used = pulls(show.shooter || '');
  if (riteBeat.value === 'end') {
    if (n < used) return 'spent';
    if (n === used) return show.hit ? 'hit' : 'empty';
    return '';
  }
  if (n <= used) return 'spent';
  if (n === used + 1 && riteBeat.value === 'gun') return 'now';
  return '';
}

const gunSrc = '/assets/tavern/revolver.png?v=2';
const winStage = '/assets/tavern/victory-stage.jpg';
const winPetals = '/assets/tavern/victory-petals.jpg';
const exitStage = '/assets/tavern/defeat-stage.jpg';
const exitAsh = '/assets/tavern/defeat-ash.jpg';
const FACE_SRC: Record<string, string> = {
  you: '/assets/tavern/face-ke.jpg',
  qin: '/assets/tavern/face-xiao.jpg',
  bar: '/assets/tavern/face-ai.jpg',
};
function faceOf(id: string) {
  return FACE_SRC[id] || '';
}
function acting(id: string) {
  return state.value?.turn === id || focusId.value === id;
}
const riteFace = computed(() => {
  if (riteBeat.value !== 'gun' && riteBeat.value !== 'end') return '';
  return faceOf(state.value?.show?.shooter || '');
});
const gunPose = computed(() => {
  if (riteBeat.value === 'gun') return 'cocked';
  if (riteBeat.value === 'end' && state.value?.show?.hit) return 'bang';
  if (riteBeat.value === 'end') return 'dry';
  return '';
});
const boardRows = computed(() => {
  const saved = state.value?.board || {};
  return (['you', 'qin', 'her', 'bar'] as const).map((id) => ({
    id,
    name: nameOf(id),
    played: saved[id]?.played || 0,
    wins: saved[id]?.wins || 0,
    points: saved[id]?.points || 0,
  }));
});

watch(selected, () => pushBoard());

watch([deckId, styleId, copy], () => {
  saveCardDeck(deckId.value);
  saveCardStyle(styleId.value);
  const map: Record<string, string> = {};
  for (const id of ['loli', 'girl', 'lady', 'pup', 'boy', 'sire', 'mei', 'ying']) map[id] = faceName(id);
  setFaceNames(map);
  refreshCardArt();
  pushBoard();
}, { immediate: true });

onMounted(() => {
  if (!characters.list.length) void characters.loadList();
  mountTavern(toggle);
  stage.camSizeLock = ['threeQ', 'full'];
  stage.playShot('threeQ', false, 1.1);
  chat.pauseSidecar();
  void primeShot();
  void primeApplause();
  void primeCollapse();
  window.addEventListener('keydown', onKey);
  void send('refresh');
});
onUnmounted(() => {
  stop();
  unmountTavern();
  stage.camSizeLock = null;
  window.removeEventListener('keydown', onKey);
  if (triumphTimer) window.clearTimeout(triumphTimer);
});
</script>

<template>
  <div class="tavern" :class="{ shock, bang: muzzle, tense: riteBeat === 'gun', 'has-focus': !!focusId }">
    <header>
      <div>
        <h1>{{ copy.title }}</h1>
      </div>
      <div class="head-actions">
        <button type="button" class="ghost" @click="boardOpen = !boardOpen">{{ copy.board }}</button>
        <button v-if="!lobby" type="button" class="ghost" :disabled="busy" @click="endNight">{{ t('tavern.endNight') }}</button>
        <button v-if="lobby" type="button" class="gold" :disabled="busy" @click="enter">{{ copy.enter }}</button>
        <button type="button" class="ghost" @click="closeTavern">{{ t('tavern.leaveScene') }}</button>
      </div>
    </header>

    <div v-if="boardOpen" class="board">
      <p v-for="row in boardRows" :key="row.id">
        <b>{{ row.name }}</b>
        <span>{{ row.played }} {{ copy.played }}</span>
        <span>{{ row.wins }} {{ copy.wins }}</span>
        <span>{{ row.points > 0 ? '+' : '' }}{{ row.points }} {{ copy.pts }}</span>
      </p>
    </div>

    <div v-if="lobby" class="picks">
      <p>{{ t('tavern.pickWho') }}</p>
      <div>
        <button v-for="who in characters.list" :key="who.id" type="button" :class="characters.currentId === who.id ? 'gold' : 'ghost'" :disabled="busy" @click="pickWho(who.id)">{{ who.name }}</button>
      </div>
      <p>{{ t('tavern.pickDeck') }}</p>
      <div>
        <button v-for="deck in CARD_DECKS" :key="deck" type="button" :class="deckId === deck ? 'gold' : 'ghost'" @click="deckId = deck">{{ t('tavern.deck.' + deck) }}</button>
      </div>
      <p>{{ t('tavern.pickStyle') }}</p>
      <div>
        <button v-for="look in CARD_STYLES" :key="look" type="button" :class="styleId === look ? 'gold' : 'ghost'" @click="styleId = look">{{ t('tavern.style.' + look) }}</button>
      </div>
    </div>
    <p v-if="lobby" class="rules">{{ copy.rules }}</p>

    <div v-else class="marks">
      <p class="who her" :class="{ turn: state?.turn === 'her', dead: !alive('her'), out: !!seatOf.her?.out, focus: focusId === 'her', leaving: farewell === 'her', victor: triumph?.id === 'her' }">
        <span v-if="shownCards('her')" class="minis tiny">
          <img v-for="n in shownCards('her')" :key="n" :src="artUrl('back')" alt="" />
        </span>
        <span class="face" :class="{ live: acting('her') }">
          <b class="mono">{{ (state?.her_name || copy.seat.her).slice(0, 1) }}</b>
          <span class="wave"></span>
          <span class="wave late"></span>
        </span>
        <span class="rounds"><i v-for="n in 3" :key="n" :class="{ spent: n <= pulls('her') }" /></span>
        <b>{{ state?.her_name || copy.seat.her }}</b>
        <em v-if="focusId === 'her'" class="mark">{{ focusText }}</em>
        <span>{{ seatMark('her') }}</span>
      </p>
      <p class="who qin" :class="{ turn: state?.turn === 'qin', dead: !alive('qin'), out: !!seatOf.qin?.out, focus: focusId === 'qin', leaving: farewell === 'qin', victor: triumph?.id === 'qin' }">
        <span v-if="shownCards('qin')" class="minis">
          <img v-for="n in shownCards('qin')" :key="n" :src="artUrl('back')" alt="" />
        </span>
        <span class="face" :class="{ live: acting('qin') }">
          <img :src="faceOf('qin')" alt="" />
          <span class="wave"></span>
          <span class="wave late"></span>
        </span>
        <span class="rounds"><i v-for="n in 3" :key="n" :class="{ spent: n <= pulls('qin') }" /></span>
        <b>{{ copy.seat.qin }}</b>
        <em v-if="focusId === 'qin'" class="mark">{{ focusText }}</em>
        <span>{{ seatMark('qin') }}</span>
      </p>
      <p class="who bar" :class="{ turn: state?.turn === 'bar', dead: !alive('bar'), out: !!seatOf.bar?.out, focus: focusId === 'bar', leaving: farewell === 'bar', victor: triumph?.id === 'bar' }">
        <span v-if="shownCards('bar')" class="minis">
          <img v-for="n in shownCards('bar')" :key="n" :src="artUrl('back')" alt="" />
        </span>
        <span class="face" :class="{ live: acting('bar') }">
          <img :src="faceOf('bar')" alt="" />
          <span class="wave"></span>
          <span class="wave late"></span>
        </span>
        <span class="rounds"><i v-for="n in 3" :key="n" :class="{ spent: n <= pulls('bar') }" /></span>
        <b>{{ copy.seat.bar }}</b>
        <em v-if="focusId === 'bar'" class="mark">{{ focusText }}</em>
        <span>{{ seatMark('bar') }}</span>
      </p>
      <div v-if="state?.table" class="tablecard">
        <span class="pip">
          <img :src="artUrl(`${state.table}:1`)" alt="" />
          <b>{{ faceName(state.table) }}</b>
          <b class="flip">{{ faceName(state.table) }}</b>
        </span>
        <div>
          <p>{{ copy.truth }}</p>
          <b>{{ faceName(state.table) }}</b>
        </div>
      </div>
      <p class="who you" :class="{ turn: state?.turn === 'you', dead: !alive('you'), out: !!seatOf.you?.out, focus: focusId === 'you', leaving: farewell === 'you', victor: triumph?.id === 'you' }">
        <span class="face" :class="{ live: acting('you') }">
          <img :src="faceOf('you')" alt="" />
          <span class="wave"></span>
          <span class="wave late"></span>
        </span>
        <span class="rounds"><i v-for="n in 3" :key="n" :class="{ spent: n <= pulls('you') }" /></span>
        <b>{{ copy.seat.you }}</b>
        <em v-if="focusId === 'you'" class="mark">{{ focusText }}</em>
        <em v-if="!alive('you')">{{ copy.dead }}</em>
        <em v-else-if="seatOf.you?.out">{{ copy.aside }}</em>
        <em v-else-if="!(state?.you?.hand || []).length && (state?.phase === 'act' || state?.phase === 'name')">{{ copy.bye }}</em>
      </p>
    </div>

    <div v-if="farewell" class="farewell">
      <img class="stage" :src="exitStage" alt="" />
      <img class="ash" :src="exitAsh" alt="" />
      <div class="cast">
        <span class="face huge">
          <img v-if="faceOf(farewell)" :src="faceOf(farewell)" alt="" />
          <b v-else class="mono">{{ nameOf(farewell).slice(0, 1) }}</b>
        </span>
      </div>
      <p class="banner">{{ copy.exitTitle }}</p>
      <p class="words">{{ copy.exitLine(nameOf(farewell)) }}</p>
    </div>
    <div v-if="triumph" class="triumph">
      <img class="stage" :src="winStage" alt="" />
      <img class="petals" :src="winPetals" alt="" />
      <div class="cast">
        <span class="face huge">
          <img v-if="faceOf(triumph.id)" :src="faceOf(triumph.id)" alt="" />
          <b v-else class="mono">{{ nameOf(triumph.id).slice(0, 1) }}</b>
        </span>
      </div>
      <p class="banner">{{ copy.triumphTitle }}</p>
      <p class="words">{{ copy.triumphLine(nameOf(triumph.id), triumph.rank) }}</p>
    </div>

    <div v-if="state?.phase === 'show'" class="rite">
      <p v-if="state.show?.kind === 'reveal'" class="tag">{{ riteBeat === 'flip' ? copy.flipTitle : copy.riteTitle }}</p>
      <p v-if="log.length" class="quote">{{ log[log.length - 1].text }}</p>
      <p class="words">{{ riteWords }}</p>
      <div v-if="riteFace" class="victim" :class="{ hit: riteBeat === 'end' && state.show?.hit, safe: riteBeat === 'end' && state.show && !state.show.hit }">
        <span class="face big" :class="{ live: riteBeat === 'gun' || (riteBeat === 'end' && state.show?.hit), smug: riteBeat === 'end' && state.show && !state.show.hit }">
          <img :src="riteFace" alt="" />
          <span class="wave"></span>
          <span class="wave late"></span>
        </span>
      </div>
      <div v-if="state.show?.kind === 'reveal' && riteBeat && riteBeat !== 'flip'" class="gun" :class="gunPose">
        <img :src="gunSrc" alt="" />
        <i class="flash" />
        <i class="blast" />
      </div>
      <div v-if="state.show?.kind === 'reveal' && riteBeat !== 'flip'" class="chambers">
        <i v-for="n in 3" :key="n" :class="chamberClass(n)" />
      </div>
      <button v-if="riteReady" type="button" class="gold" :disabled="busy" @click="cont">{{ copy.goon }}</button>
    </div>

    <ul v-if="shownLog.length && !lobby" class="said">
      <li v-for="row in shownLog" :key="row.seq" :class="{ now: row.seq === shownLog[shownLog.length - 1].seq }">
        <em v-if="row.verb">{{ row.verb }}</em>
        <span>{{ row.text }}</span>
      </li>
    </ul>

    <div class="dock">
      <p v-if="hint" class="hint">{{ hint }}</p>
      <p v-if="error" class="error">{{ error }}</p>
      <div v-if="tableEmpty" class="btns">
        <button type="button" class="gold" :disabled="busy" @click="onNext">{{ copy.nextRound }}</button>
      </div>
      <div v-else-if="canName" class="btns suits">
        <button v-for="face in suits" :key="face" type="button" class="gold" :disabled="busy" @click="onName(face)">
          {{ faceName(face) }}
        </button>
      </div>
      <div v-if="!lobby && !tableEmpty && state?.phase === 'act'" class="btns">
        <button type="button" class="gold" :disabled="!canAct || !selected.length" @click="onPlay">
          {{ copy.play }}<span v-if="selected.length"> · {{ selected.length }}</span>
        </button>
        <button type="button" class="ghost" :disabled="!canCall" @click="onCall">{{ copy.call }}</button>
      </div>
      <div v-if="state?.phase === 'over'" class="sheet">
        <p class="line">{{ copy.sayWin(nameOf(state.winner || '')) }}</p>
        <ul v-if="state.places?.length" class="places">
          <li v-for="row in state.places" :key="row.id">
            {{ copy.scoreLine(row.tag || '', row.rank || 0, nameOf(row.id), row.points) }}
          </li>
        </ul>
        <p v-if="coinNote" class="line">{{ coinNote }}</p>
        <p class="line">{{ copy.againHint }}</p>
        <button type="button" class="gold" :disabled="busy" @click="enter">{{ copy.again }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tavern {
  position: absolute;
  inset: 0;
  z-index: 40;
  pointer-events: none;
  color: #f6efe4;
  font-family: "Palatino Linotype", "Songti SC", "SimSun", serif;
}
.tavern.shock::after {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(120, 16, 24, 0.28);
  animation: kick 0.45s ease;
}
.tavern.bang { animation: quake 0.55s linear; }
.tavern.bang::after {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(255, 246, 220, 0.92);
  animation: kick 0.22s ease;
  pointer-events: none;
}
.board {
  position: absolute;
  top: 78px;
  right: 22px;
  z-index: 4;
  pointer-events: auto;
  min-width: 230px;
  padding: 12px 16px;
  border-radius: 14px;
  background: rgba(12, 8, 16, 0.88);
  border: 1px solid rgba(231, 194, 122, 0.4);
}
.board p {
  display: flex;
  gap: 10px;
  margin: 7px 0;
  letter-spacing: 0.08em;
  font-size: 14px;
}
.board b { min-width: 3.2em; }
.gun {
  position: relative;
  width: min(520px, 88vw);
  margin: 8px auto 0;
}
.gun img {
  width: 100%;
  display: block;
  transform-origin: 28% 55%;
}
.gun.cocked { animation: jitters 0.08s linear 0.85s infinite; }
.gun.cocked img { animation: raise 0.9s ease forwards; }
.gun.dry img { animation: twitch 0.16s ease-out; }
.gun.bang img { animation: recoil 0.22s ease-out; }
.victim { display: flex; justify-content: center; margin: 8px 0 0; }
.victim.hit .face img { animation: tremble 0.05s linear infinite; filter: saturate(0.2) contrast(1.2); }
.victim.hit .wave { border-color: #ff6a6a; }
.gun .blast {
  position: absolute;
  right: 8%;
  top: 18%;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 3px solid rgba(255, 70, 50, 0.9);
  opacity: 0;
  pointer-events: none;
}
.gun.bang .blast { animation: sonar 0.7s ease-out; }
.gun .flash {
  position: absolute;
  right: -4%;
  top: 8%;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: radial-gradient(circle, #fff 0%, #ffe08a 28%, #ff5a1a 58%, transparent 74%);
  opacity: 0;
  pointer-events: none;
}
.gun.bang .flash { animation: muzzle 0.28s linear forwards; }
.places { list-style: none; margin: 0; padding: 0; }
.places li { margin: 2px 0; letter-spacing: 0.12em; }
header, .dock, .rules {
  pointer-events: none;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 18px 22px 0;
}
.head-actions, .btns, .sheet { pointer-events: auto; }
.head-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; max-width: min(520px, 62vw); }
.head-actions button.ghost { margin-left: 0; }
.kicker {
  margin: 0;
  letter-spacing: 0.42em;
  font-size: 12px;
  color: #e7c27a;
}
h1 {
  margin: 4px 0 0;
  font-size: 28px;
  font-weight: 500;
  letter-spacing: 0.28em;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.65);
}
button {
  border: 1px solid rgba(240, 212, 138, 0.45);
  background: transparent;
  color: inherit;
  border-radius: 999px;
  padding: 8px 18px;
  letter-spacing: 0.16em;
  cursor: pointer;
}
button.gold { background: #e7c27a; color: #2a1c10; border-color: transparent; }
button.ghost { margin-left: 8px; }
.suits button + button { margin-left: 8px; }
button:disabled { opacity: 0.45; cursor: default; }
.picks {
  position: absolute;
  top: 72px;
  right: 22px;
  z-index: 12;
  width: min(320px, 42vw);
  display: flex;
  flex-direction: column;
  gap: 6px;
  text-align: right;
  pointer-events: auto;
  padding: 12px 14px 14px;
  border-radius: 14px;
  background: rgba(12, 8, 16, 0.88);
  border: 1px solid rgba(231, 194, 122, 0.4);
}
.picks p {
  margin: 8px 0 0;
  font-size: 12px;
  letter-spacing: 0.22em;
  color: #e7c27a;
}
.picks div { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
.picks button { margin: 0; padding: 6px 10px; letter-spacing: 0.08em; }
.rules {
  position: absolute;
  top: 78px;
  left: 22px;
  width: min(280px, 34vw);
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  text-align: left;
  color: rgba(246, 239, 228, 0.9);
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.85);
}
.marks { position: absolute; inset: 0; }
.who {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  margin: 0;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.85);
  letter-spacing: 0.12em;
}
.minis { display: flex; gap: 3px; }
.minis img {
  width: 22px;
  height: 32px;
  object-fit: cover;
  border-radius: 3px;
  border: 1px solid rgba(231, 194, 122, 0.75);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.45);
}
.minis.tiny img { width: 16px; height: 24px; }
.rounds { display: flex; gap: 4px; }
.rounds i {
  width: 14px;
  height: 14px;
  border-radius: 2px;
  background: #f0d48a;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.55), 0 0 8px rgba(231, 194, 122, 0.45);
}
.rounds i.spent {
  background: rgba(255, 255, 255, 0.06);
  box-shadow: inset 0 0 0 2px rgba(231, 194, 122, 0.95);
}
.who.turn b, .who.focus b { color: #fff6d0; text-shadow: 0 0 14px rgba(255, 214, 120, 0.9); }
.who.dead { opacity: 0.45; }
.face {
  position: relative;
  width: 46px;
  height: 46px;
  flex: none;
}
.face img, .face .mono {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  object-fit: cover;
  object-position: center 18%;
  border: 1px solid rgba(231, 194, 122, 0.75);
  position: relative;
  z-index: 1;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.45);
}
.face .mono {
  display: grid;
  place-items: center;
  margin: 0;
  background: #2a1c28;
  color: #f3e2b8;
  font-size: 18px;
  font-weight: 500;
  letter-spacing: 0;
}
.face .wave {
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  border: 2px solid rgba(231, 194, 122, 0.85);
  opacity: 0;
  pointer-events: none;
}
.face.live img, .face.live .mono { animation: tremble 0.16s linear infinite; }
.face.live .wave { animation: sonar 1.15s ease-out infinite; }
.face.live .wave.late { animation-delay: 0.5s; }
.face.big { width: 92px; height: 92px; }
.face.big img, .face.big .mono { width: 92px; height: 92px; font-size: 36px; }
.who.leaving .face img,
.who.leaving .face .mono { animation: drop-face 1.15s ease-in forwards; }
.who.victor .face img,
.who.victor .face .mono { animation: rise-face 1.05s ease-out; }
.who.victor .face .wave { border-color: #fff1c2; animation: sonar 0.9s ease-out infinite; }
.farewell, .triumph {
  position: absolute;
  inset: 0;
  z-index: 8;
  overflow: hidden;
  pointer-events: none;
  background: #07040a;
}
.farewell .stage, .triumph .stage {
  position: absolute;
  inset: -8%;
  width: 116%;
  height: 116%;
  object-fit: cover;
  animation: stage-in 4.6s ease-out forwards;
}
.triumph .petals, .farewell .ash {
  position: absolute;
  left: 0;
  top: -20%;
  width: 100%;
  height: 140%;
  object-fit: cover;
  mix-blend-mode: screen;
  animation: particle-fall 4.4s linear forwards;
}
.farewell .cast, .triumph .cast {
  position: absolute;
  left: 50%;
  top: 58%;
  z-index: 2;
}
.triumph .cast { animation: rise-cast 1.05s cubic-bezier(0.16, 0.84, 0.32, 1) forwards; }
.farewell .cast { animation: fall-cast 1.85s ease-in forwards; }
.face.huge { width: 156px; height: 156px; }
.face.huge img, .face.huge .mono {
  width: 156px;
  height: 156px;
  font-size: 64px;
  border-width: 3px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.65), 0 0 36px rgba(255, 214, 120, 0.4);
}
.farewell .face.huge img, .farewell .face.huge .mono {
  border-color: #e07070;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7), 0 0 28px rgba(180, 20, 30, 0.45);
}
.farewell .banner, .triumph .banner {
  position: absolute;
  left: 50%;
  bottom: 13%;
  z-index: 3;
  margin: 0;
  transform: translateX(-50%);
  padding: 8px 28px;
  border-radius: 999px;
  background: rgba(8, 4, 8, 0.78);
  letter-spacing: 0.48em;
  font-size: 28px;
}
.triumph .banner { color: #ffe7a8; border: 1px solid rgba(231, 194, 122, 0.85); }
.farewell .banner { color: #ffb4b4; border: 1px solid rgba(210, 64, 64, 0.85); }
.farewell .words, .triumph .words {
  position: absolute;
  left: 50%;
  bottom: 7%;
  z-index: 3;
  margin: 0;
  transform: translateX(-50%);
  font-size: 18px;
  letter-spacing: 0.16em;
  color: #fff6e8;
  text-shadow: 0 2px 10px #000;
}
.face.smug img { animation: boast 0.5s ease; }
.who.dead .face img { filter: grayscale(1) brightness(0.55); }
.who.out { opacity: 0.62; }
.tavern.has-focus .who:not(.focus) { opacity: 0.38; }
.who .mark {
  margin-left: 4px;
  padding: 1px 8px;
  border-radius: 999px;
  background: #e7c27a;
  color: #2a1c10;
  font-style: normal;
  letter-spacing: 0.16em;
  font-size: 12px;
}
.tavern.tense::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(ellipse at center, rgba(80, 0, 0, 0.08) 10%, rgba(0, 0, 0, 0.86) 72%);
  animation: vignette 0.7s ease-in-out infinite;
}
.tavern.tense .rite {
  width: min(680px, 94vw);
  background: rgba(12, 2, 4, 0.9);
  border-color: rgba(190, 48, 48, 0.8);
  box-shadow: 0 0 48px rgba(140, 0, 0, 0.45);
}
.rite {
  position: absolute;
  left: 50%;
  top: 148px;
  transform: translateX(-50%);
  width: min(460px, 84vw);
  z-index: 2;
  pointer-events: auto;
  text-align: center;
  padding: 16px 22px 14px;
  border-radius: 18px;
  background: rgba(10, 8, 14, 0.82);
  border: 1px solid rgba(231, 194, 122, 0.38);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45);
}
.rite .quote {
  margin: 0 0 8px;
  color: #fff6d0;
  letter-spacing: 0.08em;
  font-size: 16px;
}
.rite .tag {
  margin: 0 0 8px;
  letter-spacing: 0.42em;
  font-size: 12px;
  color: #e7c27a;
}
.rite .words {
  margin: 0;
  font-size: 18px;
  line-height: 1.65;
  letter-spacing: 0.06em;
}
.chambers {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 14px;
}
.chambers i {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  box-shadow: inset 0 0 0 1.5px rgba(231, 194, 122, 0.85);
  background: transparent;
}
.chambers i.spent { background: rgba(231, 194, 122, 0.28); }
.chambers i.now {
  width: 22px;
  height: 22px;
  background: #fff1c2;
  box-shadow: 0 0 18px #ffe7a8;
  animation: pulse 0.72s ease-in-out infinite;
}
.chambers i.empty { background: transparent; }
.chambers i.hit { background: #e07070; box-shadow: none; }
.rite button { margin-top: 14px; }
@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.82); opacity: 0.55; }
}
.her { top: 132px; left: 25%; transform: translateX(-50%); }
.qin { top: 34%; left: 16px; }
.bar { top: 34%; right: 16px; }
.you { bottom: 156px; left: 50%; transform: translateX(-50%); }
.you .face,
.you .rounds {
  position: absolute;
  left: 50%;
  z-index: 3;
}
.you .face { bottom: -128px; transform: translateX(-50%); }
.you .rounds { bottom: -146px; transform: translateX(-50%); }
.tablecard {
  position: absolute;
  top: 96px;
  left: 22px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.tablecard .pip {
  position: relative;
  width: 54px;
  height: 80px;
  flex: 0 0 auto;
}
.tablecard img {
  width: 54px;
  height: 80px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid rgba(231, 194, 122, 0.75);
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.5);
}
.tablecard .pip b {
  position: absolute;
  left: 2px;
  top: 2px;
  padding: 0 2px;
  font-size: 8px;
  line-height: 1.2;
  letter-spacing: 0;
  color: #f3d48a;
  background: rgba(12, 8, 16, 0.78);
}
.tablecard .pip b.flip {
  left: auto;
  top: auto;
  right: 2px;
  bottom: 2px;
  transform: rotate(180deg);
}
.tablecard p {
  margin: 0;
  letter-spacing: 0.28em;
  font-size: 12px;
  color: #e7c27a;
}
.tablecard b {
  display: block;
  margin-top: 4px;
  font-size: 22px;
  font-weight: 500;
  letter-spacing: 0.18em;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.85);
}
.who em { font-style: normal; color: #e7b4b4; }
.dock {
  position: absolute;
  left: 50%;
  bottom: 78px;
  transform: translateX(-50%);
  width: min(640px, 92vw);
  text-align: center;
}
.hint, .line, .error {
  margin: 0 0 8px;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.85);
}
.said {
  position: absolute;
  left: 16px;
  bottom: 108px;
  z-index: 3;
  list-style: none;
  margin: 0;
  padding: 6px 10px;
  width: min(240px, 28vw);
  max-height: 148px;
  overflow: hidden;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.34);
  text-align: left;
}
.said li {
  display: flex;
  gap: 6px;
  align-items: baseline;
  margin: 0;
  padding: 2px 0;
  color: rgba(255, 244, 220, 0.55);
  font-size: 12px;
  line-height: 1.35;
}
.said li.now { color: #fff6df; }
.said em {
  flex: 0 0 auto;
  min-width: 36px;
  font-style: normal;
  font-size: 12px;
  letter-spacing: 0.12em;
  color: #e7c27a;
}
.error { color: #ffb4b4; }
.sheet {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  border-radius: 16px;
  background: rgba(12, 8, 16, 0.72);
}
@keyframes kick {
  0% { opacity: 0; }
  30% { opacity: 1; }
  100% { opacity: 0; }
}
@keyframes raise {
  from { transform: rotate(2deg) translateY(10px); }
  to { transform: rotate(-7deg) translateY(-4px); }
}
@keyframes twitch {
  0% { transform: rotate(-7deg); }
  40% { transform: rotate(-2deg) translateX(-6px); }
  100% { transform: rotate(-7deg); }
}
@keyframes tremble {
  0% { transform: translate(0, 0) rotate(0deg); }
  25% { transform: translate(-1.5px, 1px) rotate(-2deg); }
  50% { transform: translate(1.5px, -1px) rotate(1.5deg); }
  75% { transform: translate(-1px, -1px) rotate(-1deg); }
  100% { transform: translate(0, 0) rotate(0deg); }
}
@keyframes sonar {
  0% { transform: scale(0.8); opacity: 0.85; }
  100% { transform: scale(1.7); opacity: 0; }
}
@keyframes boast {
  0% { transform: scale(1) rotate(0deg); }
  40% { transform: scale(1.08) rotate(-4deg); }
  100% { transform: scale(1) rotate(0deg); }
}
@keyframes jitters {
  0% { transform: translate(0, 0); }
  25% { transform: translate(-2px, 1px); }
  50% { transform: translate(3px, -1px); }
  75% { transform: translate(-2px, -1px); }
  100% { transform: translate(0, 0); }
}
@keyframes vignette {
  0%, 100% { opacity: 0.85; }
  50% { opacity: 1; }
}
@keyframes recoil {
  0% { transform: rotate(-8deg) translate(0, 0); }
  20% { transform: rotate(-28deg) translate(-120px, 30px); }
  100% { transform: rotate(-6deg) translate(0, 0); }
}
@keyframes muzzle {
  0% { opacity: 1; transform: scale(0.2); }
  30% { opacity: 1; transform: scale(1.15); }
  100% { opacity: 0; transform: scale(1.8); }
}
@keyframes quake {
  0%, 100% { transform: translate(0, 0); }
  12% { transform: translate(-14px, 8px); }
  28% { transform: translate(16px, -12px); }
  46% { transform: translate(-10px, 6px); }
  64% { transform: translate(7px, -4px); }
  82% { transform: translate(-3px, 2px); }
}
@keyframes drop-face {
  0% { transform: translateY(0) scale(1) rotate(0deg); filter: none; }
  16% { transform: translate(-5px, 1px) rotate(-8deg); filter: contrast(1.5) saturate(0.15); }
  100% { transform: translateY(70px) scale(0.55) rotate(18deg); filter: grayscale(1) brightness(0.3); opacity: 0.15; }
}
@keyframes rise-face {
  0% { transform: translateY(16px) scale(0.82); }
  50% { transform: translateY(-12px) scale(1.14); }
  100% { transform: translateY(0) scale(1); }
}
@keyframes fall-off {
  0% { transform: translateY(0) scale(1); opacity: 1; filter: none; }
  12% { transform: translate(-8px, 4px) rotate(-6deg); filter: contrast(1.4) saturate(0.2); }
  100% { transform: translateY(46vh) scale(0.7) rotate(22deg); opacity: 0; filter: grayscale(1) brightness(0.25); }
}
@keyframes lift {
  0% { transform: translateY(18px) scale(0.86); }
  60% { transform: translateY(-8px) scale(1.06); }
  100% { transform: translateY(0) scale(1); }
}
@keyframes stage-in {
  0% { transform: scale(1.14); }
  100% { transform: scale(1); }
}
@keyframes particle-fall {
  0% { transform: translateY(-6%); opacity: 0.15; }
  18% { opacity: 1; }
  100% { transform: translateY(18%); opacity: 0.9; }
}
@keyframes rise-cast {
  0% { transform: translate(-50%, -10%) scale(0.62); opacity: 0; }
  100% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
}
@keyframes fall-cast {
  0% { transform: translate(-50%, -50%) scale(1.05) rotate(0deg); opacity: 1; filter: none; }
  14% { transform: translate(-50%, -42%) rotate(-8deg); filter: contrast(1.4) saturate(0.2); }
  100% { transform: translate(-50%, 72vh) scale(0.7) rotate(22deg); opacity: 0; filter: grayscale(1) brightness(0.25); }
}
</style>
