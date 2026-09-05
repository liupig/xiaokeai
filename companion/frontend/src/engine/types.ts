import type * as THREE from 'three';

export type BoneKey =
  | 'hips' | 'spine' | 'chest' | 'head'
  | 'leftUpperArm' | 'rightUpperArm' | 'rightLowerArm';

export type ExprKey = 'aa' | 'blink' | 'happy' | 'angry' | 'sad' | 'relaxed';
export type EmotionKey = 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed';
export type ActionKey = 'nod' | 'shake';
export type Axis = 'x' | 'y' | 'z';
export type CamPreset = 'close' | 'half' | 'full';
export type CamShotId =
  | CamPreset
  | 'bust' | 'threeQ' | 'long'
  | 'high45'
  | 'yawL45' | 'yawR45'
  | 'yawL90' | 'yawR90';

/** 每根被程序驱动的手臂：摆动轴与方向 */
export interface ArmRig {
  axis: Axis;
  down: number; // 从静止姿势放下手臂需要叠加的角度（带符号）
  up: number;   // 挥手抬起时叠加的角度（带符号）
}

/** 统一的角色抽象：PMX / VRM / GLB 三种模型共用 */
export interface Avatar {
  isVRM: boolean;
  bone(key: BoneKey): THREE.Object3D | null;
  /** 每帧表情写入前调用，清空上一帧的形态键 */
  beginFrame(): void;
  setExpr(key: ExprKey, v: number): void;
  /** 模型自带的全部形态键名 */
  morphNames(): string[];
  /** 按名字直接驱动任意形态键 */
  setMorph(name: string, v: number): void;
  update(dt: number): void;
  /** 骨骼初始欧拉角追踪，动画在其基础上叠加 */
  base(obj: THREE.Object3D): THREE.Euler;
  armL: ArmRig;
  armR: ArmRig;
}

export type MorphEntry = { name: string; scale: number };
export type MorphMap = Record<ExprKey, MorphEntry[]>;
export type BoneMap = Record<BoneKey | 'leftLowerArm', string[]>;

export interface QualityOptions {
  physics: boolean;
  pixelRatioCap: number;
  /** 灯光亮度倍率（0.5~1.5，默认 1） */
  lightLevel: number;
}
