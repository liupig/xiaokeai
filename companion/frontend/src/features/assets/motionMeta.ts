/** 动作类别：下载页 / 动作库 / 角色卡共用 */

import { api, encodeAssetPath, type AssetItem } from '../../api/client';
import { stage } from '../../engine/stage';

export type MotionCat = 'idle' | 'greet' | 'interact' | 'dance';

export const MOTION_CATS: { key: MotionCat; label: string }[] = [
  { key: 'idle', label: '待机' },
  { key: 'greet', label: '打招呼' },
  { key: 'interact', label: '互动' },
  { key: 'dance', label: '舞蹈' },
];

const CAT_SET = new Set<string>(MOTION_CATS.map((c) => c.key));
const PREFIX = /^\[(?:待机|打招呼|互动|舞蹈|特写|环绕|推拉|定镜|电影)\]\s*/;

export function stripCatPrefix(label: string) {
  return (label || '').replace(PREFIX, '').trim();
}

export function parseMotionCat(m: { label: string; name: string; meta?: string }): MotionCat {
  try {
    const cat = JSON.parse(m.meta || '{}').category;
    if (CAT_SET.has(cat)) return cat as MotionCat;
  } catch { /* 旧数据 */ }
  const t = `${m.label}${m.name}`.replace(/g[- ]?idle|\(g\)-?idle/ig, ' ');
  if (/待机|待機|闲置|站姿|姿势 Pose|艾尔海森姿势/.test(t)) return 'idle';
  if (/打招呼|挥手|招手|问好|问候|再见|挨拶|wave|hello|摆手|举手/i.test(t)) return 'greet';
  if (/互动|比心|飞吻|害羞|思考|托腮|叉腰|点头|摇头|鼓掌|歪头|伸懒腰|坐下|坐姿|说话|鞠躬|卖萌|撩人|比耶|蹲坐|抱膝|摊手|拒绝|郁闷|格挡|捂胸|眨眼|轻拍|病娇|走路|叽里呱啦/.test(t)) {
    return 'interact';
  }
  return 'dance';
}

export function guessWorkCat(name: string): MotionCat {
  return parseMotionCat({ label: name, name, meta: '{}' });
}

export function catLabel(cat: MotionCat) {
  return MOTION_CATS.find((c) => c.key === cat)?.label ?? cat;
}

/** 从资产 meta.bgm 拼出可播放的 /assets/... 地址。只有舞蹈才带音乐。 */
export function motionBgmUrl(asset: { label?: string; name?: string; meta?: string }): string | undefined {
  if (parseMotionCat({
    label: asset.label || '',
    name: asset.name || '',
    meta: asset.meta,
  }) !== 'dance') return undefined;
  try {
    const bgm = JSON.parse(asset.meta || '{}').bgm;
    if (typeof bgm === 'string' && bgm.trim()) {
      return '/assets/' + encodeAssetPath(bgm);
    }
  } catch { /* 旧数据 */ }
  return undefined;
}

let danceLib: string[] = [];
let danceLibReady: Promise<void> | null = null;
let lastLibBgm = '';

export function setDanceMusicLibrary(urls: string[]) {
  danceLib = urls.filter(Boolean);
}

/** 拉一次 assets/music 曲库；之后复用。 */
export function ensureDanceMusicLibrary() {
  if (!danceLibReady) {
    danceLibReady = api.listMusic()
      .then((tracks) => {
        setDanceMusicLibrary(tracks.map((t) => `/assets/${encodeAssetPath(t.path)}`));
      })
      .catch(() => {
        danceLibReady = null;
      });
  }
  return danceLibReady;
}

function pickDanceLibraryBgm(): string | undefined {
  if (!danceLib.length) return undefined;
  const pool = danceLib.length < 2 ? danceLib : danceLib.filter((u) => u !== lastLibBgm);
  const pick = pool[Math.floor(Math.random() * pool.length)];
  if (!pick) return undefined;
  lastLibBgm = pick;
  return pick;
}

/** 播 VMD，若资产绑了 BGM / 镜头则同步开停。舞蹈有专属歌用专属；没有就从曲库随机抽，跟歌停。 */
export function playAssetMotion(
  asset: AssetItem,
  opts?: { once?: boolean; holdLast?: boolean; skipCamera?: boolean; onEnded?: () => void },
) {
  const dance = parseMotionCat(asset) === 'dance';
  if (dance) stage.holdDance();
  const bound = dance ? motionBgmUrl(asset) : undefined;
  const play = (bgm?: string) => stage.playMotion(api.assetUrl(asset), {
    once: opts?.once ?? (dance ? true : undefined),
    holdLast: opts?.holdLast,
    dance,
    bgm,
    camera: opts?.skipCamera ? undefined : motionCameraUrl(asset),
    onEnded: opts?.onEnded,
  });
  if (dance && !bound) {
    return ensureDanceMusicLibrary().then(() => play(pickDanceLibraryBgm()));
  }
  return play(bound);
}

/** 从资产 meta.camera 拼出镜头 VMD 地址 */
export function motionCameraUrl(asset: { meta?: string }): string | undefined {
  try {
    const cam = JSON.parse(asset.meta || '{}').camera;
    if (typeof cam === 'string' && cam.trim()) {
      return '/assets/' + encodeAssetPath(cam);
    }
  } catch { /* 旧数据 */ }
  return undefined;
}
