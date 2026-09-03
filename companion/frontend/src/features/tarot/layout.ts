import * as THREE from 'three';

/** 与后端 plays.py celtic_xy / choice_xy 对齐，单位约一张牌宽。 */
const CELTIC: [number, number][] = [
  [0.0, 0.0],
  [0.08, 0.12],
  [0.0, -0.34],
  [-0.34, 0.0],
  [0.0, 0.34],
  [0.34, 0.0],
  [0.78, -0.42],
  [0.78, -0.14],
  [0.78, 0.14],
  [0.78, 0.42],
];

const CHOICE: [number, number][] = [
  [-0.42, 0.28],
  [-0.42, 0.0],
  [-0.42, -0.28],
  [0.42, 0.28],
  [0.42, 0.0],
  [0.42, -0.28],
  [0.0, -0.02],
];

export type TarotLayout = 'row' | 'choice' | 'celtic' | string;

export function cardScale(n: number) {
  if (n >= 10) return 0.68;
  if (n >= 7) return 0.78;
  if (n >= 5) return 0.88;
  return 1;
}

export function slotOf(
  layout: TarotLayout,
  n: number,
  i: number,
  chestY: number,
  out: THREE.Vector3,
) {
  const z = n >= 8 ? 0.48 : 0.56;
  const y = chestY - 0.02;
  if (layout === 'celtic') {
    const [x, yy] = CELTIC[i] || [0, 0];
    out.set(x * 0.92, y + yy * 0.55, z + Math.abs(x) * 0.04);
    return out;
  }
  if (layout === 'choice') {
    const [x, yy] = CHOICE[i] || [0, 0];
    out.set(x * 1.05, y + yy * 0.62, z);
    return out;
  }
  const gap = n <= 1 ? 0 : (n <= 3 ? 0.34 : Math.min(0.22, 0.92 / n));
  const span = gap * Math.max(0, n - 1);
  const x = n === 1 ? 0 : -span / 2 + gap * i;
  const bias = n >= 3 ? -0.08 : 0;
  out.set(x + bias, y, z + i * 0.01);
  return out;
}

export function clarifierOffset(host: THREE.Vector3, out: THREE.Vector3) {
  out.copy(host);
  out.x += 0.11;
  out.y += 0.05;
  out.z += 0.03;
  return out;
}
