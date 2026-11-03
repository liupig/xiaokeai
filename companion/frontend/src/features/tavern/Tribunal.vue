<script setup lang="ts">
import { computed } from 'vue';
import { t } from '../../i18n';
const props = defineProps<{
  beat: string; locked: boolean; hit: boolean;
  rotation: number; chamber: number; name: string; portrait: string;
  words: string; verdict: string; ready: boolean; busy: boolean;
}>();
defineEmits<{ continue: [] }>();
const outcome = computed(() => props.beat === 'end');
const stage = computed(() => outcome.value ? (props.hit ? 'hit' : 'safe') : props.beat === 'verdict' ? 'verdict' : props.locked ? 'locked' : 'spin');
const headline = computed(() => props.beat === 'verdict' ? props.verdict : t(`tavern.tribunal.${stage.value}`));
const bores = [{ x: 130, y: 56 }, { x: 194, y: 167 }, { x: 66, y: 167 }];
</script>

<template>
  <section class="tribunal" :class="stage" :aria-label="t('tavern.tribunal.title')">
    <div class="atmosphere" aria-hidden="true" />
    <div class="subject-shadow" :style="portrait ? { backgroundImage: `url(${portrait})` } : {}" aria-hidden="true" />
    <div class="shock-curtain" aria-hidden="true" />
    <svg v-if="stage === 'hit'" class="fracture" viewBox="0 0 1000 700" preserveAspectRatio="none" aria-hidden="true">
      <g fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M512 326 430 241 384 224 279 96 241 0M512 326 600 239 641 223 721 86 804 0M512 326 635 344 706 318 859 345 1000 304M512 326 553 451 534 480 609 579 628 700M512 326 387 359 346 411 176 436 0 527M512 326 444 440 388 479 322 700"/>
        <path d="m430 241 9-66-44-49m202 115 67 17 41-14m1 74 19-56 65-23M553 451l62 39 10 57M387 359l-63-26-49 11m169 96-68-4-30 38" opacity=".5"/>
      </g>
    </svg>
    <div class="letterbox top" aria-hidden="true" /><div class="letterbox bottom" aria-hidden="true" />
    <div class="tribunal-content">
      <div class="scene-heading">
        <span class="eyebrow">{{ t('tavern.tribunal.title') }}</span>
        <span class="serial">{{ String(chamber).padStart(2, '0') }} / 03</span>
      </div>
      <div class="scene-body">
        <div class="subject">
          <div class="portrait-frame">
            <img v-if="portrait" :src="portrait" alt="" />
            <span v-else class="initial">{{ name.slice(0, 1) }}</span>
            <span class="portrait-scan" aria-hidden="true" />
            <span class="portrait-corner" aria-hidden="true" />
          </div>
          <span class="subject-caption">{{ t('tavern.tribunal.subject') }}</span>
          <strong class="subject-name">{{ name }}</strong>
        </div>
        <div class="mechanism" aria-hidden="true">
          <div class="dial-halo" />
          <svg class="cylinder" viewBox="0 0 260 260" :style="{ transform: `rotate(${rotation}deg)` }">
            <defs>
              <radialGradient id="tribunal-steel"><stop stop-color="#4d5050"/><stop offset=".65" stop-color="#25282b"/><stop offset="1" stop-color="#0b0d10"/></radialGradient>
              <radialGradient id="tribunal-bore"><stop stop-color="#020304"/><stop offset=".75" stop-color="#08090b"/><stop offset="1" stop-color="#3c3730"/></radialGradient>
            </defs>
            <circle cx="130" cy="130" r="119" fill="url(#tribunal-steel)" stroke="#8b7c63" stroke-width="2"/>
            <circle cx="130" cy="130" r="111" fill="none" stroke="#b2a68a" stroke-opacity=".24" stroke-dasharray="2 9"/>
            <g v-for="(bore, i) in bores" :key="i" :class="{ current: i === chamber - 1, spent: i < chamber - 1 }">
              <circle :cx="bore.x" :cy="bore.y" r="35" fill="url(#tribunal-bore)" stroke="#625849" stroke-width="3"/>
              <circle :cx="bore.x" :cy="bore.y" r="28" class="bore-light" fill="none" stroke="#bda780" stroke-opacity=".15"/>
              <circle v-if="outcome && hit && i === chamber - 1" :cx="bore.x" :cy="bore.y" r="17" fill="#b97f48" stroke="#e5bf83" stroke-width="2"/>
            </g>
            <circle cx="130" cy="130" r="15" fill="#080a0c" stroke="#756c5b" stroke-width="3"/>
            <path d="M122 130h16M130 122v16" stroke="#9c8c70" stroke-width="2"/>
          </svg>
          <div class="dial-pointer" />
          <svg class="sidearm" viewBox="0 0 360 180" aria-hidden="true">
            <defs><linearGradient id="tribunal-gunmetal" x2="0" y2="1"><stop stop-color="#a6a29b"/><stop offset=".18" stop-color="#53585d"/><stop offset=".55" stop-color="#181c22"/><stop offset="1" stop-color="#555658"/></linearGradient></defs>
            <path d="M22 37h174l11-11h44l13 19 31 15 9 25-20 16 26 58-31 14-39-62-25-9-38-2-16-16H22z" fill="url(#tribunal-gunmetal)" stroke="#9e9586" stroke-width="1.4"/>
            <path d="M28 43h139v26H28zM35 31h13v6H35zM160 31h17v6h-17z" fill="#30353a" stroke="#8c8981"/>
            <path d="M31 50h127M31 62h127" stroke="#bcb3a1" stroke-opacity=".4"/>
            <rect x="176" y="38" width="57" height="48" rx="9" fill="#242a30" stroke="#88867c"/>
            <path d="M185 43v37M198 43v37M211 43v37M224 43v37" stroke="#a4a397" stroke-opacity=".5" stroke-width="3"/>
            <path d="M229 100c-1 29 37 36 41 3M242 100q-9 17 8 18" fill="none" stroke="#8d897f" stroke-width="4"/>
            <path d="M262 104l24 55 15-7-25-55" fill="#201b1a" stroke="#73665a"/>
            <path d="M243 27l8-12 10 3-3 21" fill="#4c4b49" stroke="#9e9586"/>
          </svg>
          <span class="muzzle-bloom" />
          <div class="impact-ring" />
        </div>
        <div class="resolution">
          <span class="micro">{{ t('tavern.tribunal.oneBullet') }}</span>
          <h2 :key="stage">{{ headline }}</h2>
          <div class="tension-line" aria-hidden="true"><i /></div>
          <p class="scene-words" aria-live="polite">{{ words }}</p>
          <div class="chamber-ledger" :aria-label="`${chamber} / 3`">
            <span v-for="n in 3" :key="n" :class="{ used: n < chamber, active: n === chamber }">0{{ n }}</span>
          </div>
        </div>
      </div>
      <ol class="scene-steps">
        <li :class="{ active: beat === 'verdict' }"><b>01</b>{{ t('tavern.tribunal.verdict') }}</li>
        <li :class="{ active: beat === 'gun' }"><b>02</b>{{ t('tavern.tribunal.spin') }}</li>
        <li :class="{ active: outcome }"><b>03</b>{{ t('tavern.tribunal.result') }}</li>
      </ol>
      <button v-if="ready" type="button" class="resume" :disabled="busy" @click="$emit('continue')">{{ t('tavern.tribunal.continue') }}</button>
    </div>
  </section>
</template>

<style scoped>
.tribunal { --accent: #c3aa7d; position: absolute; inset: 0; z-index: 6; overflow: hidden; display: grid; place-items: center; color: #ece5d7; background: radial-gradient(ellipse at 48% 46%, #202126 0, #0d0e12 45%, #030407 85%); pointer-events: none; font-family: 'Songti SC', Georgia, serif; animation: scene-arrive .55s ease-out; }
.atmosphere { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, transparent 0 3px, #ffffff03 4px 5px), radial-gradient(ellipse at 70% 50%, #7c231313, transparent 65%); box-shadow: inset 0 0 120px 45px #0009; }
.letterbox { position: absolute; height: clamp(30px, 8vh, 90px); inset-inline: 0; background: #020305; z-index: 2; }
.letterbox.top { top: 0; border-bottom: 1px solid #ffffff0b; }.letterbox.bottom { bottom: 0; border-top: 1px solid #ffffff0b; }
.tribunal-content { position: relative; width: min(1020px, 88%); padding-block: 24px; }
.scene-heading { display: flex; justify-content: space-between; border-bottom: 1px solid #c3aa7d35; padding-bottom: 20px; }
.eyebrow, .serial, .micro, .subject-caption, .scene-steps, .chamber-ledger { font: 11px/1.6 system-ui, sans-serif; letter-spacing: .22em; color: #9b9489; }
.eyebrow { color: var(--accent); }.serial { font-variant-numeric: tabular-nums; }
.scene-body { display: grid; grid-template-columns: 160px minmax(160px, 310px) minmax(160px, 1fr); gap: clamp(18px, 4vw, 60px); align-items: center; padding-block: clamp(22px, 5vh, 64px); }
.subject { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; }
.portrait-frame { width: 134px; height: 174px; position: relative; border: 1px solid #b4a18155; background: #15171b; box-shadow: 12px 12px 0 #ffffff03; overflow: hidden; }
.portrait-frame img { width: 100%; height: 100%; object-fit: cover; object-position: center 20%; filter: saturate(.25) contrast(1.15); }
.initial { display: grid; height: 100%; place-items: center; font-size: 64px; color: #c3aa7d; }
.portrait-scan { position: absolute; inset: 0; background: linear-gradient(transparent 40%, #000a); }
.portrait-corner { position: absolute; inset: 5px; border: 1px solid #c3aa7d28; }
.subject-caption { margin-top: 8px; font-size: 10px; }.subject-name { font-size: 25px; letter-spacing: .12em; font-weight: 400; overflow-wrap: anywhere; }
.mechanism { position: relative; aspect-ratio: 1; width: 100%; }
.cylinder { width: 100%; position: relative; filter: drop-shadow(0 18px 22px #000); transition: transform .7s cubic-bezier(.12,.7,.22,1); }
.dial-halo { position: absolute; inset: -10%; border: 1px solid #c3aa7d22; border-radius: 50%; box-shadow: 0 0 70px #c3aa7d0a; }
.dial-halo::after { content: ''; position: absolute; inset: -8%; border: 1px dashed #c3aa7d15; border-radius: 50%; }
.dial-pointer { position: absolute; top: -9%; left: calc(50% - 4px); width: 8px; height: 17px; background: var(--accent); clip-path: polygon(0 0,100% 0,50% 100%); }
.sidearm { position: absolute; width: 110%; left: -4%; bottom: -11%; opacity: .7; filter: drop-shadow(0 12px 14px #000); transform-origin: 80% 50%; }
.spin .sidearm { animation: weapon-raise 1s ease-out both; }
.locked .sidearm { opacity: 1; }
.hit .sidearm { animation: weapon-kick .28s ease-out; }
.safe .sidearm { animation: dry-recoil .22s ease-out; }
.muzzle-bloom { position: absolute; left: -9%; bottom: 7%; width: 50%; aspect-ratio: 1; background: radial-gradient(ellipse, #fff9e8 0, #edb674 16%, #d86c2722 42%, transparent 68%); opacity: 0; pointer-events: none; }
.hit .muzzle-bloom { animation: weapon-flash .16s ease-out; }
@keyframes weapon-raise { from { transform: translateY(25px) rotate(8deg); opacity: 0; } to { transform: translateY(0); opacity: .7; } }
@keyframes weapon-kick { 20% { transform: translateX(14px) rotate(8deg); } to { transform: none; } }
@keyframes weapon-flash { 10% { opacity: .9; } to { opacity: 0; } }
.resolution { min-width: 0; }.micro { font-size: 10px; color: #8b8172; }
h2 { margin: 14px 0 22px; font-size: clamp(28px, 4vw, 52px); line-height: 1.25; letter-spacing: .13em; font-weight: 400; color: var(--accent); animation: title-enter .4s ease-out; }
.tension-line { height: 1px; background: #c3aa7d20; overflow: hidden; }.tension-line i { display: block; width: 100%; height: 100%; background: var(--accent); transform-origin: left; }
.scene-words { min-height: 4.8em; margin: 18px 0; color: #b8b2a8; font-size: 15px; line-height: 1.8; overflow-wrap: anywhere; }
.chamber-ledger { display: flex; gap: 14px; }.chamber-ledger span { border-bottom: 2px solid #ffffff12; padding: 3px 6px 7px; color: #57575a; }.chamber-ledger .used { text-decoration: line-through; }.chamber-ledger .active { color: var(--accent); border-color: var(--accent); }
.scene-steps { list-style: none; padding: 18px 0 0; margin: 0; border-top: 1px solid #c3aa7d25; display: flex; justify-content: space-between; gap: 12px; }.scene-steps li { display: flex; gap: 12px; }.scene-steps b { font-weight: 400; color: #545458; }.scene-steps .active, .scene-steps .active b { color: var(--accent); }
.spin .dial-halo { animation: pressure-breathe .8s ease-in-out infinite alternate; }.spin .tension-line i { animation: tighten 2.8s ease-out both; }.spin .portrait-frame { animation: pressure-breathe 1s ease-in-out infinite alternate; }
.locked { --accent: #e4c6a0; }.locked .cylinder { filter: drop-shadow(0 0 20px #b2613033); }.locked .tension-line i { transform: scaleX(.02); }
.safe { --accent: #a7c1b6; }.safe .dial-halo { border-color: #a7c1b655; }.safe .cylinder { animation: dry-recoil .22s ease-out; }.safe .portrait-frame img { filter: saturate(.55); }
.hit { --accent: #db7766; }.hit .tribunal-content { animation: impact-cut .5s ease-out; }.hit .portrait-frame img { animation: subject-fall 1.2s ease-in forwards; }.hit .atmosphere { background: radial-gradient(ellipse at center, #4a0e1233, #070408 75%); }
.impact-ring { position: absolute; inset: 5%; border: 1px solid #f1bd91; border-radius: 50%; opacity: 0; }.hit .impact-ring { animation: impact-wave .9s ease-out; }.hit .bore-light { stroke: #b45c4c; }
.resume { margin: 20px auto 0; display: block; pointer-events: auto; border: 1px solid #c3aa7d66; background: #111217; color: #e8d9ba; padding: 10px 28px; cursor: pointer; }.resume:focus-visible { outline: 2px solid #c3aa7d; outline-offset: 4px; }
@keyframes scene-arrive { from { opacity: 0; } to { opacity: 1; } }
@keyframes title-enter { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: translateY(0); } }
@keyframes pressure-breathe { from { box-shadow: 0 0 12px #a2692510; } to { box-shadow: 0 0 40px #a2692533; } }
@keyframes tighten { from { transform: scaleX(.05); } to { transform: scaleX(1); } }
@keyframes dry-recoil { 40% { translate: 0 3px; } }
@keyframes impact-cut { 15% { transform: translate(-9px, 3px); filter: brightness(1.6); } 35% { transform: translate(6px,-2px); } 65% { transform: translate(-2px,0); } }
@keyframes impact-wave { from { opacity: .8; transform: scale(.8); } to { opacity: 0; transform: scale(1.7); } }
@keyframes subject-fall { to { transform: translateY(30px); filter: grayscale(1) brightness(.35); } }
@media(max-width: 700px) { .scene-body { grid-template-columns: 96px 1fr; gap: 24px; padding-block: 22px; }.portrait-frame { width: 88px; height: 116px; }.mechanism { width: min(180px, 100%); justify-self: center; }.resolution { grid-column: 1 / -1; }.resolution h2 { margin: 6px 0 12px; }.scene-words { min-height: 0; margin-block: 12px; }.subject-name { font-size: 20px; }.scene-steps { letter-spacing: 0; font-size: 10px; }.letterbox { height: 24px; } }
@media(max-height: 620px) and (min-width: 701px) { .scene-body { padding-block: 20px; }.portrait-frame { width: 100px; height: 128px; }.mechanism { max-width: 200px; justify-self: center; }.scene-words { font-size: 13px; }.tribunal-content { width: min(1000px, 90%); }.letterbox { height: 20px; } }

/* 越接近击发，镜头越近；冲击只出现一次，不用循环闪屏代替惊吓。 */
.subject-shadow { position: absolute; inset: -10%; background-position: 14% 35%; background-size: cover; opacity: .065; filter: grayscale(1) contrast(1.8) blur(6px); mask-image: linear-gradient(90deg, #000, transparent 75%); transition: opacity .7s; }
.scene-body { perspective: 800px; }
.spin .tribunal-content { animation: dread-camera 4.5s cubic-bezier(.2,.1,.6,1) both; }
.spin .atmosphere { animation: dread-vignette .65s ease-in-out infinite alternate; }
.spin .mechanism { animation: cylinder-approach 3.5s ease-out both; }
.spin .portrait-frame img { animation: nervous-breath .55s ease-in-out infinite alternate; }
.locked .tribunal-content { transform: scale(1.07); transition: transform .8s ease-in; }
.locked .mechanism { transform: scale(1.18) rotate(-3deg); transition: transform .8s cubic-bezier(.2,.7,.3,1); }
.locked .subject-shadow { opacity: .15; }
.locked .portrait-frame { box-shadow: 0 0 45px #9b262653; border-color: #d58f77; }
.locked .scene-heading, .locked .scene-steps { opacity: .3; transition: opacity .6s; }
.locked h2 { color: #f0d4b7; text-shadow: 0 0 35px #c9654c66; }
.shock-curtain { position: absolute; inset: 0; z-index: 4; pointer-events: none; opacity: 0; }
.hit .shock-curtain { animation: shot-shutter .9s ease-out both; }
.hit .tribunal-content { animation: brutal-impact .8s cubic-bezier(.1,.8,.2,1) both; }
.hit h2 { animation: verdict-slam .65s cubic-bezier(.16,.8,.3,1) both; color: #f19a83; text-shadow: 3px 0 #b3132766, -3px 0 #e7d8c144; }
.hit .portrait-frame { animation: portrait-strike .8s ease-out both; border-color: #cb6652; }
.hit .portrait-frame img { animation: victim-drop 1.25s ease-in both; }
.hit .atmosphere { background: radial-gradient(ellipse at center, #8d1d2844, #070408 73%); }
.hit .sidearm { animation: heavy-recoil .45s cubic-bezier(.1,.9,.3,1); opacity: 1; }
.hit .impact-ring { border-width: 3px; animation: impact-wave .65s ease-out; }
.fracture { position: absolute; inset: 0; width: 100%; height: 100%; color: #ded0bd; z-index: 3; pointer-events: none; animation: glass-hit 1s ease-out both; }
.safe .tribunal-content { animation: empty-startle .32s ease-out; }
.safe .portrait-frame { transition: box-shadow .8s .3s; box-shadow: 0 0 25px #a7c1b622; }
@keyframes dread-camera { from { transform: scale(.96); } to { transform: scale(1.04); } }
@keyframes cylinder-approach { from { transform: scale(.92) rotate(2deg); } to { transform: scale(1.1) rotate(-2deg); } }
@keyframes dread-vignette { to { box-shadow: inset 0 0 160px 65px #000c, inset 0 0 50px #7f172622; } }
@keyframes nervous-breath { to { transform: scale(1.045) translateY(-2px); filter: saturate(.1) contrast(1.3); } }
@keyframes shot-shutter { 0% { opacity: .85; background: #ffe8c8; } 8% { opacity: 1; background: #120105; } 25% { opacity: .75; background: #080104; } 100% { opacity: 0; background: #080104; } }
@keyframes brutal-impact { 0% { transform: scale(1.18) translate(-16px,8px) rotate(-1.2deg); filter: contrast(1.8); } 15% { transform: scale(1.1) translate(12px,-5px) rotate(.8deg); } 30% { transform: scale(1.07) translate(-7px,3px); } 55% { transform: scale(1.04) translate(3px,-1px); } 100% { transform: scale(1); filter: contrast(1); } }
@keyframes verdict-slam { from { transform: scale(1.7); opacity: .1; filter: blur(5px); } to { transform: scale(1); opacity: 1; filter: blur(0); } }
@keyframes portrait-strike { 20% { transform: rotate(-7deg) translateY(7px); } 50% { transform: rotate(2deg); } to { transform: rotate(-2deg); } }
@keyframes victim-drop { 15% { transform: scale(1.15) translateX(-7px); filter: grayscale(1) contrast(2); } to { transform: translateY(45px) scale(1.1); filter: grayscale(1) brightness(.18); } }
@keyframes heavy-recoil { 12% { transform: translate(35px,-14px) rotate(19deg) scale(1.15); } 40% { transform: translate(12px,4px) rotate(-4deg); } to { transform: none; } }
@keyframes glass-hit { from { opacity: .6; transform: scale(.97); } 35% { opacity: .25; } to { opacity: 0; transform: scale(1.035); } }
@keyframes empty-startle { 20% { transform: scale(1.065) translateY(5px); } 50% { transform: scale(1.025) translateY(-2px); } to { transform: scale(1); } }

@media(prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } .shock-curtain, .fracture { display: none; } .tribunal-content, .mechanism { transform: none !important; } }
</style>
