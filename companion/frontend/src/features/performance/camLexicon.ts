/**
 * 运镜库卡片：内置环绕/螺旋 + 下载的电影镜头。
 * 景别由审查的 size 决定；这里只标这条镜头适合在多远的景别里抽。
 */
import type { AssetItem } from '../../api/client';
import type { Distance, Grade } from './lexicon';
import { DIST_MAX } from './lexicon';

export interface CamCard {
  name: string;
  label: string;
  grade: Grade;
  minDist: Distance;
  maxDist: Distance;
  /** 只在跳舞 / 全身展示时用（电影镜头、环绕一周） */
  showOnly: boolean;
}

/** 绑死特写/全身等景别的旧内置镜头，审查和抽卡都不要再出现 */
const FRAMING_CAM_RE =
  /特写定镜|半身定镜|全身定镜|仰拍定镜|俯拍定镜|缓推特写|拉出全身|升起俯拍|低机位推进|呼吸运镜/;

function textOf(a: { name: string; label: string }) {
  return `${a.label || ''} ${a.name}`;
}

export function isFramingCam(a: { name: string; label: string }) {
  return FRAMING_CAM_RE.test(textOf(a).replace(/^\[(?:特写|环绕|推拉|定镜|电影|舞蹈)\]\s*/, ''));
}

export function classifyCam(a: AssetItem): CamCard {
  const name = a.name;
  const label = a.label || name;
  const t = textOf(a).replace(/^\[(?:特写|环绕|推拉|定镜|电影|舞蹈)\]\s*/, '');

  const card = (over: Partial<CamCard>): CamCard => {
    const minDist = over.minDist ?? 'half';
    return {
      name,
      label,
      grade: over.grade ?? 'B',
      minDist,
      maxDist: over.maxDist ?? DIST_MAX[minDist],
      showOnly: over.showOnly ?? false,
    };
  };

  if (/左侧环绕|右侧环绕/.test(t)) return card({ minDist: 'bust', maxDist: 'long', grade: 'A' });
  if (/弧线扫过/.test(t)) return card({ minDist: 'bust', maxDist: 'long', grade: 'A' });
  if (/环绕一周|螺旋一周|螺旋上升/.test(t)) {
    return card({ minDist: 'half', maxDist: 'long', grade: 'B', showOnly: true });
  }
  if (/妄想天使/i.test(t)) {
    return card({ minDist: 'full', maxDist: 'long', grade: 'S', showOnly: true });
  }
  if (/镜头|カメラ|camera/i.test(t)) {
    return card({ minDist: 'full', maxDist: 'long', grade: 'A', showOnly: true });
  }
  return card({ minDist: 'half', maxDist: 'full', grade: 'B' });
}

export function buildCamCards(cameras: AssetItem[]): CamCard[] {
  return cameras.filter((c) => !isFramingCam(c)).map(classifyCam);
}
