import * as THREE from 'three';
import type { Live2DModel } from 'untitled-pixi-live2d-engine/cubism';
import type { ArmRig, Avatar, BoneKey, ExprKey, TouchZone } from '../types';
import { makeBaseTracker } from '../avatar/common';

type CoreParameterModel = {
  getParameterCount(): number;
  getParameterId(index: number): { getString(): string | { s: string } };
  getParameterMinimumValue(index: number): number;
  getParameterMaximumValue(index: number): number;
  getParameterDefaultValue(index: number): number;
  getParameterValueByIndex(index: number): number;
  setParameterValueByIndex(index: number, value: number): void;
};

export interface Live2DParameterMeta {
  id: string;
  name: string;
  min: number;
  max: number;
  defaultValue: number;
  value: number;
}

type ExpressionDefinition = {
  Parameters?: { Id: string; Value: number; Blend?: string }[];
};

const STANDARD_PARAMS: Record<ExprKey, [id: string, scale: number][]> = {
  aa: [['ParamMouthOpenY', 1], ['ParamParmOpenY', 1]],
  blink: [['ParamEyeLOpen', -1], ['ParamEyeROpen', -1]],
  happy: [['ParamMouthFormY', 1], ['ParamMouthForm', 1], ['ParamEyeSmile', 1]],
  angry: [['ParamBrowLY', -1], ['ParamBrowRY', -1], ['ParamMouthFormY', -1], ['ParamMouthForm', -1]],
  sad: [['ParamBrowLY', 1], ['ParamBrowRY', 1], ['ParamMouthFormY', -1], ['ParamMouthForm', -1]],
  relaxed: [['ParamMouthFormY', 0.35], ['ParamMouthForm', 0.35]],
};

const BONE_PARAMS: Partial<Record<BoneKey, { x?: string; y?: string; z?: string }>> = {
  head: { x: 'ParamAngleY', y: 'ParamAngleX', z: 'ParamAngleZ' },
  chest: { x: 'ParamBodyAngleY', z: 'ParamBodyAngleZ' },
  spine: { x: 'ParamBodyAngleY', z: 'ParamBodyAngleZ' },
};

const ACTION_GROUPS: Record<string, string[]> = {
  greet: ['Greet', 'Wave', 'Hello', 'TapBody', 'Touch', '挥手', '打招呼', '竖手指打开', '默认手切举手'],
  think: ['Think', 'Thinking', '思考'],
  talk: ['Talk', 'Speaking', '说话', '抚胸手打开', '默认手切举手'],
  bow: ['Bow', '鞠躬'],
  clap: ['Clap', 'Applause', '鼓掌'],
  heart: ['Heart', 'Cute', '比心', '爱心', '抚胸手打开'],
  shy: ['Shy', '害羞', '脸红', '抚胸手打开'],
  comfort: ['Comfort', '安慰', '抱抱', '抚胸手打开'],
  tease: ['Tease', '调皮', '逗弄', '狗尾巴草打开'],
  cute: ['Cute', '可爱', '卖萌', '竖手指打开'],
  look: ['Look', '看向'],
  stretch: ['Stretch', '伸懒腰'],
  idle: ['Idle', 'Idling', '待机'],
};
const SOCIAL_ACTIONS = new Set(['greet', 'heart', 'cute', 'comfort', 'tease', 'shy']);

export class Live2DAvatar implements Avatar {
  readonly isVRM = false;
  readonly root = new THREE.Object3D();
  readonly armL: ArmRig = { axis: 'z', down: 0, up: 0 };
  readonly armR: ArmRig = { axis: 'z', down: 0, up: 0 };
  readonly base = makeBaseTracker();

  private readonly bones = new Map<BoneKey, THREE.Object3D>();
  private readonly parameterIds: string[];
  private readonly expressionNames: string[] = [];
  private readonly expressionFiles = new Map<string, string>();
  private readonly expressionDefinitions = new Map<string, ExpressionDefinition>();
  private readonly enabledExpressions = new Set<string>();
  private readonly expressionSeqs = new Map<string, number>();
  private readonly values = new Map<string, number>();
  private readonly manual = new Map<string, number>();
  private readonly persistent = new Map<string, number>();
  private readonly suppressed = new Set<string>();
  private labels = new Map<string, string>();
  private actionName = '';
  private actionTime = 0;
  private actionSeq = 0;
  private nativeAction = false;
  private nativeFinish: (() => void) | null = null;
  private nativeTimer: ReturnType<typeof setTimeout> | null = null;
  private autoActionNextAt = 0;
  private lastAutoGroup = '';
  private gazeEnabled = true;
  private gazeTarget = { x: 0, y: 0 };
  private gazeCurrent = { x: 0, y: 0 };
  actionActive = false;

  constructor(private readonly model: Live2DModel) {
    const core = this.core;
    this.parameterIds = Array.from({ length: core.getParameterCount() }, (_, index) => {
      const id = core.getParameterId(index).getString();
      return typeof id === 'string' ? id : id.s;
    });
    const settings = model.internalModel.settings.json as {
      FileReferences?: {
        Expressions?: { Name?: string; File: string }[];
        Motions?: Record<string, unknown[]>;
      };
    };
    for (const item of settings.FileReferences?.Expressions ?? []) {
      if (!item.Name) continue;
      this.expressionNames.push(item.Name);
      this.expressionFiles.set(item.Name, model.internalModel.settings.resolveURL(item.File));
    }
    const positions: [BoneKey, number][] = [
      ['hips', 0.85], ['spine', 1.05], ['chest', 1.2], ['head', 1.5],
      ['leftUpperArm', 1.2], ['rightUpperArm', 1.2], ['rightLowerArm', 1.0],
    ];
    for (const [key, y] of positions) {
      const bone = new THREE.Object3D();
      bone.position.y = y;
      this.root.add(bone);
      this.bones.set(key, bone);
    }
  }

  private get core(): CoreParameterModel {
    return this.model.internalModel.coreModel as CoreParameterModel;
  }

  bone(key: BoneKey): THREE.Object3D | null {
    return this.bones.get(key) ?? null;
  }

  beginFrame() {
    this.values.clear();
  }

  setExpr(key: ExprKey, value: number) {
    for (const [name, scale] of STANDARD_PARAMS[key]) {
      if (!this.parameterIds.includes(name)) continue;
      const current = this.values.get(name);
      const next = key === 'blink' ? 1 - value : value * scale;
      if (current === undefined || Math.abs(next) >= Math.abs(current)) {
        this.values.set(name, next);
      }
    }
  }

  morphNames(): string[] {
    return [...this.parameterIds, ...this.expressionNames];
  }

  setMorph(name: string, value: number) {
    const previous = this.manual.get(name) ?? 0;
    this.manual.set(name, value);
    if (this.expressionNames.includes(name)) {
      const manager = this.model.internalModel.motionManager.expressionManager;
      if (value > 0 && previous <= 0) void this.model.expression(name);
      else if (value <= 0 && previous > 0) manager?.resetExpression();
    }
  }

  private playAutoNative(group: string, index: number): boolean {
    const now = Date.now();
    if (now < this.autoActionNextAt) return true;
    this.lastAutoGroup = group;
    this.autoActionNextAt = now + 10000 + Math.random() * 5000;
    return this.playNativeMotion(group, index);
  }

  playAction(name: string): boolean {
    const motions = this.motionDefinitions;
    const aliases = ACTION_GROUPS[name] ?? [];
    const groups = Object.keys(motions).filter((key) =>
      aliases.some((alias) => alias.toLowerCase() === key.toLowerCase()));
    if (groups.length) {
      const fresh = groups.filter((group) => group !== this.lastAutoGroup);
      const candidates = fresh.length ? fresh : groups;
      const group = candidates[Math.floor(Math.random() * candidates.length)];
      return this.playAutoNative(group, 0);
    }
    if (SOCIAL_ACTIONS.has(name)) {
      const fallback = Object.keys(motions).find((key) => /^(touch|tapbody|touchbody|action)$/i.test(key));
      if (fallback) {
        const index = Math.floor(Math.random() * motions[fallback].length);
        return this.playAutoNative(fallback, index);
      }
    }
    const seq = ++this.actionSeq;
    this.actionName = name;
    this.actionTime = 0;
    this.actionActive = true;
    this.nativeAction = false;
    return seq > 0;
  }

  playNativeMotion(group: string, index: number): boolean {
    const motions = this.motionDefinitions;
    const definition = motions[group]?.[index] as { File?: string } | undefined;
    if (!definition) return false;
    this.nativeFinish?.();
    const seq = ++this.actionSeq;
    const snapshot = this.parameterIds.map((_, parameterIndex) =>
      this.core.getParameterValueByIndex(parameterIndex));
    let finished = false;
    const finish = () => {
      if (finished || seq !== this.actionSeq) return;
      finished = true;
      if (this.nativeTimer) clearTimeout(this.nativeTimer);
      this.nativeTimer = null;
      this.nativeFinish = null;
      this.model.stopMotions();
      snapshot.forEach((value, parameterIndex) =>
        this.core.setParameterValueByIndex(parameterIndex, value));
      this.actionActive = false;
      const idle = Object.keys(motions).find((key) => /^(idling|idle)$/i.test(key));
      if (idle) void this.model.motion(idle, 0, 1).catch(() => {});
    };
    const finishAfter = (ms: number) => {
      if (seq === this.actionSeq) this.nativeTimer = setTimeout(finish, ms);
    };
    this.nativeFinish = finish;
    this.actionName = group;
    this.actionTime = 0;
    this.actionActive = true;
    this.nativeAction = true;
    if (definition.File) {
      const url = this.model.internalModel.settings.resolveURL(definition.File);
      void fetch(url).then((response) => {
        if (!response.ok) throw new Error('motion metadata unavailable');
        return response.json() as Promise<{ Meta?: { Duration?: number } }>;
      }).then((data) => {
        const seconds = Number(data.Meta?.Duration);
        finishAfter(Number.isFinite(seconds) && seconds > 0
          ? Math.min(15000, Math.max(300, seconds * 1000 + 100))
          : 2500);
      }).catch(() => finishAfter(2500));
    } else {
      finishAfter(2500);
    }
    void this.model.motion(group, index, 2, {
      onFinish: finish,
      onError: finish,
    }).catch(finish);
    return true;
  }

  stopNativeMotion() {
    this.nativeFinish?.();
  }

  playTouch(): boolean {
    const groups = this.motionGroups;
    const touch = groups.find((item) => item.group.toLowerCase() === 'touch');
    const group = touch ?? groups.find((item) => item.group.toLowerCase() === 'action');
    if (!group) {
      const reactions = ['comfort', 'shy', 'tease'];
      return this.playAction(reactions[Math.floor(Math.random() * reactions.length)]);
    }
    return this.playNativeMotion(group.group, Math.floor(Math.random() * group.count));
  }

  private get motionDefinitions(): Record<string, unknown[]> {
    const settings = this.model.internalModel.settings.json as {
      FileReferences?: { Motions?: Record<string, unknown[]> };
    };
    return settings.FileReferences?.Motions ?? {};
  }

  get motionGroups(): { group: string; count: number }[] {
    return Object.entries(this.motionDefinitions).map(([group, items]) => ({ group, count: items.length }));
  }

  setDisplayInfo(parameters: { Id: string; Name?: string }[]) {
    this.labels = new Map(parameters.map((item) => [item.Id, item.Name || item.Id]));
  }

  parameterMeta(): Live2DParameterMeta[] {
    const core = this.core;
    return this.parameterIds.map((id, index) => ({
      id,
      name: this.labels.get(id) || id,
      min: core.getParameterMinimumValue(index),
      max: core.getParameterMaximumValue(index),
      defaultValue: core.getParameterDefaultValue(index),
      value: this.manual.get(id) ?? core.getParameterValueByIndex(index),
    }));
  }

  setParameter(id: string, value: number) {
    if (this.parameterIds.includes(id) && Number.isFinite(value)) this.manual.set(id, value);
  }

  resetParameter(id: string) {
    const index = this.parameterIds.indexOf(id);
    if (index < 0) return;
    const value = this.core.getParameterDefaultValue(index);
    this.manual.set(id, value);
    this.core.setParameterValueByIndex(index, value);
  }

  setParameterSuppressed(id: string, suppressed: boolean) {
    if (!this.parameterIds.includes(id)) return;
    if (suppressed) this.suppressed.add(id);
    else this.suppressed.delete(id);
  }

  get suppressedParameters(): string[] {
    return [...this.suppressed];
  }

  async setExpressionEnabled(name: string, enabled: boolean): Promise<void> {
    if (!this.expressionFiles.has(name)) return;
    const seq = (this.expressionSeqs.get(name) ?? 0) + 1;
    this.expressionSeqs.set(name, seq);
    if (!this.expressionDefinitions.has(name)) {
      const response = await fetch(this.expressionFiles.get(name)!);
      if (!response.ok) throw new Error(`表情资源加载失败：${name}`);
      const definition = await response.json() as ExpressionDefinition;
      if (this.expressionSeqs.get(name) !== seq) return;
      this.expressionDefinitions.set(name, definition);
    }
    if (this.expressionSeqs.get(name) !== seq) return;
    for (const parameter of this.expressionDefinitions.get(name)?.Parameters ?? []) {
      const index = this.parameterIds.indexOf(parameter.Id);
      if (index < 0) continue;
      if (enabled) this.suppressed.delete(parameter.Id);
      else this.suppressed.add(parameter.Id);
      const value = enabled ? parameter.Value : this.core.getParameterDefaultValue(index);
      this.core.setParameterValueByIndex(index, value);
    }
    if (enabled) this.enabledExpressions.add(name);
    else this.enabledExpressions.delete(name);
    this.rebuildPersistentExpressions();
  }

  async clearExpressionCategory(pattern: RegExp): Promise<void> {
    for (const name of this.expressionNames) {
      if (pattern.test(name)) await this.setExpressionEnabled(name, false);
    }
  }

  get activeExpressions(): string[] {
    return [...this.enabledExpressions];
  }

  private rebuildPersistentExpressions() {
    this.persistent.clear();
    for (const name of this.enabledExpressions) {
      const definition = this.expressionDefinitions.get(name);
      for (const parameter of definition?.Parameters ?? []) {
        const index = this.parameterIds.indexOf(parameter.Id);
        if ((parameter.Blend || 'Add') !== 'Add' || index < 0) continue;
        const base = this.persistent.get(parameter.Id) ?? this.core.getParameterDefaultValue(index);
        this.persistent.set(parameter.Id, base + parameter.Value);
      }
    }
  }

  clearNativeExpressions() {
    for (const name of this.expressionNames) this.manual.delete(name);
    this.model.internalModel.motionManager.expressionManager?.resetExpression();
  }

  setGaze(x: number, y: number) {
    this.gazeTarget.x = THREE.MathUtils.clamp(x, -1, 1);
    this.gazeTarget.y = THREE.MathUtils.clamp(y, -1, 1);
  }

  setGazeEnabled(enabled: boolean) {
    this.gazeEnabled = enabled;
    if (!enabled) this.gazeTarget = { x: 0, y: 0 };
  }

  probeTouch(x: number, y: number, width: number, height: number): TouchZone | null {
    if (x < 0 || y < 0 || x > width || y > height) return null;
    const rx = x / width;
    const ry = y / height;
    if (ry < 0.38) return 'face';
    if (ry < 0.52) return 'head';
    if (rx < 0.25 || rx > 0.75) return 'hand';
    if (ry < 0.74) return 'chest';
    return 'waist';
  }

  update(dt: number) {
    const blend = 1 - Math.exp(-10 * dt);
    this.gazeCurrent.x += (this.gazeTarget.x - this.gazeCurrent.x) * blend;
    this.gazeCurrent.y += (this.gazeTarget.y - this.gazeCurrent.y) * blend;
    const head = this.bones.get('head')!;
    if (this.actionActive && !this.nativeAction) {
      this.actionTime += dt;
      const p = Math.min(1, this.actionTime / 1.8);
      const envelope = Math.sin(Math.PI * p);
      head.rotation.set(0, 0, 0);
      if (this.actionName === 'think') {
        head.rotation.y = 0.18 * envelope;
        head.rotation.z = 0.2 * envelope;
      } else if (this.actionName === 'bow') {
        head.rotation.x = 0.4 * envelope;
      } else if (this.actionName === 'look') {
        head.rotation.y = 0.35 * envelope;
      } else {
        head.rotation.x = 0.25 * Math.sin(p * Math.PI * 4) * envelope;
      }
      if (p >= 1) {
        this.actionActive = false;
        this.actionName = '';
        head.rotation.set(0, 0, 0);
      }
    }
    if (this.nativeAction && this.actionActive) return;
    for (const [key, mapping] of Object.entries(BONE_PARAMS) as [BoneKey, typeof BONE_PARAMS[BoneKey]][]) {
      const bone = this.bones.get(key);
      if (!bone || !mapping) continue;
      if (mapping.x) this.values.set(mapping.x, THREE.MathUtils.radToDeg(bone.rotation.y));
      if (mapping.y) this.values.set(mapping.y, THREE.MathUtils.radToDeg(bone.rotation.x));
      if (mapping.z) this.values.set(mapping.z, THREE.MathUtils.radToDeg(bone.rotation.z));
    }
  }

  applyParameters() {
    const combined = new Map([...this.values, ...this.manual, ...this.persistent]);
    combined.set('ParamEyeBallX', this.gazeCurrent.x);
    combined.set('ParamEyeBallY', this.gazeCurrent.y);
    if (this.gazeEnabled && !this.actionActive) {
      combined.set('ParamAngleX', (combined.get('ParamAngleX') ?? 0) + this.gazeCurrent.x * 8);
      combined.set('ParamAngleY', (combined.get('ParamAngleY') ?? 0) - this.gazeCurrent.y * 5);
    }
    for (const [name, value] of combined) {
      const index = this.parameterIds.indexOf(name);
      if (index >= 0) this.core.setParameterValueByIndex(index, value);
    }
    for (const name of this.suppressed) {
      if (this.persistent.has(name)) continue;
      const index = this.parameterIds.indexOf(name);
      if (index >= 0) this.core.setParameterValueByIndex(index, this.core.getParameterDefaultValue(index));
    }
  }

  reset() {
    ++this.actionSeq;
    if (this.nativeTimer) clearTimeout(this.nativeTimer);
    this.nativeTimer = null;
    this.nativeFinish = null;
    this.model.stopMotions();
    this.model.internalModel.motionManager.expressionManager?.resetExpression();
    this.expressionSeqs.clear();
    for (let index = 0; index < this.parameterIds.length; index++) {
      this.core.setParameterValueByIndex(index, this.core.getParameterDefaultValue(index));
    }
    this.actionActive = false;
    this.nativeAction = false;
    this.actionName = '';
    this.autoActionNextAt = 0;
    this.lastAutoGroup = '';
    this.enabledExpressions.clear();
    this.gazeTarget = { x: 0, y: 0 };
    this.gazeCurrent = { x: 0, y: 0 };
    this.values.clear();
    this.manual.clear();
    this.persistent.clear();
    this.suppressed.clear();
  }
}
