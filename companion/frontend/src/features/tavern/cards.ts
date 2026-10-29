/** 牌组和画风。角标文字不进图，由图层自己叠。 */

export const CARD_STYLES = ['anime', 'chibi', 'real', 'solid'] as const;
export const CARD_DECKS = ['rose', 'ink'] as const;

export const DECK_FACES: Record<(typeof CARD_DECKS)[number], string[]> = {
  rose: ['loli', 'girl', 'lady'],
  ink: ['pup', 'boy', 'sire'],
};

const STYLE_KEY = 'companion.tavern.style';
const DECK_KEY = 'companion.tavern.deck';

let cardStyle: (typeof CARD_STYLES)[number] = 'anime';
let faceNames: Record<string, string> = {};

export function loadCardStyle(): (typeof CARD_STYLES)[number] {
  const raw = localStorage.getItem(STYLE_KEY) || '';
  return (CARD_STYLES as readonly string[]).includes(raw) ? (raw as (typeof CARD_STYLES)[number]) : 'anime';
}

export function loadCardDeck(): (typeof CARD_DECKS)[number] {
  const raw = localStorage.getItem(DECK_KEY) || '';
  return (CARD_DECKS as readonly string[]).includes(raw) ? (raw as (typeof CARD_DECKS)[number]) : 'rose';
}

export function saveCardStyle(style: string) {
  cardStyle = (CARD_STYLES as readonly string[]).includes(style) ? (style as (typeof CARD_STYLES)[number]) : 'anime';
  localStorage.setItem(STYLE_KEY, cardStyle);
}

export function saveCardDeck(deck: string) {
  const next = (CARD_DECKS as readonly string[]).includes(deck) ? deck : 'rose';
  localStorage.setItem(DECK_KEY, next);
}

export function cardStyleNow() {
  return cardStyle;
}

export function setFaceNames(map: Record<string, string>) {
  faceNames = { ...map };
}

export function faceMark(face: string) {
  return faceNames[face] || '';
}

cardStyle = loadCardStyle();
