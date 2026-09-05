/** 塔罗插件入口。3D 只在抽牌时动态加载。 */

export { tarotLayerOn, tarotLive, openTarotLayer, closeTarotLayer } from './gate';
export { maybeTarotPhrase, canWakeTarot, isTarotExit, isTarotRitualAllow, isTarotCut, isTarotRedeal, isTarotVoiceCommand, normTarotText } from './intent';
export {
  tarotUi,
  tarotGameLock,
  syncTarotSession,
  reconcileTarot,
  syncTarotMeta,
  prepareTarotTurn,
  drawAndSpeak,
  beginPlay,
  pickPlay,
  dismissAndSpeak,
  redealAndSpeak,
  playRitual,
  playDismiss,
  inspectCard,
  doCut,
  doPick,
  doHerDraw,
  doReveal,
  doClarifier,
  askAbout,
  afterTarotSpeak,
  ritualQuietLine,
  onCharacterSwitch,
  onModuleOff,
  armSkipIntent,
} from './session';
