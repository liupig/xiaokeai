import { mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../frontend/node_modules/esbuild/lib/main.js';
import * as THREE from '../frontend/node_modules/three/build/three.module.js';
import { FBXLoader } from '../frontend/node_modules/three/examples/jsm/loaders/FBXLoader.js';
import { Parser } from '../frontend/node_modules/three-stdlib/libs/mmdparser.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? path.resolve(root, args[index + 1]) : fallback;
};
const input = option('--input', path.resolve(root, '../_dl/mixamo'));
const output = option('--output', path.join(root, 'assets/motions'));
const model = option('--model', path.join(root, 'assets/models/qingxiao/model.pmx'));
const temp = path.join(root, 'backend/data/tmp', `mixamo-converter-${process.pid}.mjs`);

globalThis.ProgressEvent ??= class ProgressEvent {
  constructor(type, init = {}) {
    this.type = type;
    Object.assign(this, init);
  }
};

function arrayBuffer(buffer) {
  return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
}

function loadPmxRig(createMixamoRig, modelBuffer) {
  const data = new Parser().parsePmx(arrayBuffer(modelBuffer), true);
  const target = new THREE.Group();
  const bones = data.bones.map((source) => {
    const bone = new THREE.Bone();
    bone.name = source.name;
    bone.position.fromArray(source.position);
    return bone;
  });
  data.bones.forEach((source, index) => {
    if (source.parentIndex >= 0) bones[source.parentIndex].add(bones[index]);
    else target.add(bones[index]);
  });
  target.scale.setScalar(0.08);
  target.updateMatrixWorld(true);
  const rig = createMixamoRig(target, 'pmx', null);
  if (!rig) throw new Error(`无法从 ${model} 建立 PMX 人形骨骼映射`);
  return rig;
}

await mkdir(output, { recursive: true });
await mkdir(path.dirname(temp), { recursive: true });
try {
  await build({
    stdin: {
      contents: "export * from '../frontend/src/engine/mixamo.ts'; export * from '../frontend/src/engine/xkMotion.ts';",
      resolveDir: path.join(root, 'scripts'),
    },
    bundle: true,
    platform: 'node',
    format: 'esm',
    target: 'node22',
    outfile: temp,
    logLevel: 'silent',
  });
  const {
    createMixamoRig, retargetMixamoClip, createXkMotionDocument,
    parseXkMotionDocument, stringifyXkMotion,
  } = await import(`${pathToFileURL(temp).href}?t=${Date.now()}`);
  const rig = loadPmxRig(createMixamoRig, await readFile(model));
  const files = (await readdir(input)).filter((name) => name.toLowerCase().endsWith('.fbx')).sort();
  if (!files.length) throw new Error(`${input} 里没有 FBX 动作`);

  for (const file of files) {
    const source = new FBXLoader().parse(arrayBuffer(await readFile(path.join(input, file))), '');
    const name = file.replace(/\.fbx$/i, '');
    const doc = createXkMotionDocument(source, name, `Mixamo/${file}`);
    const clip = await retargetMixamoClip(source, rig);
    if (!clip) throw new Error(`${file} 没有可转换的动画轨道`);
    const restored = await parseXkMotionDocument(doc, rig);
    if (restored.tracks.length !== clip.tracks.length || restored.duration !== clip.duration) {
      throw new Error(`${file} 转换后校验失败`);
    }
    const destination = path.join(output, `${name}.xkmotion`);
    const json = stringifyXkMotion(doc);
    await writeFile(destination, json, 'utf8');
    console.log(`${file} -> ${path.relative(root, destination)} | ${clip.duration.toFixed(2)}s | ${clip.tracks.length} tracks | ${(Buffer.byteLength(json) / 1024).toFixed(0)} KiB`);
  }
} finally {
  await rm(temp, { force: true });
}
