import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MMDLoader } from '../frontend/node_modules/three-stdlib/index.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pack = path.resolve(root, process.argv[2] || 'assets/motions/xiaokeai-mixamo');
const manifest = JSON.parse(fs.readFileSync(path.join(pack, 'manifest.json'), 'utf8'));
const results = [];
for (const motion of manifest.motions) {
  const data = fs.readFileSync(path.join(pack, motion.file));
  const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
  const vmd = new MMDLoader()._getParser().parseVmd(buffer, true);
  const bones = new Set(vmd.motions.map((item) => item.boneName));
  const maxFrame = vmd.motions.reduce((max, item) => Math.max(max, item.frameNum), 0);
  const finite = vmd.motions.every((item) =>
    [...item.position, ...item.rotation].every(Number.isFinite));
  const valid = vmd.motions.length > 0 && maxFrame > 0 && finite
    && bones.has('右腕') && bones.has('左腕') && bones.has('右足') && bones.has('左足');
  results.push({ file: motion.file, label: motion.label, maxFrame, bones: bones.size, valid });
}
console.log(JSON.stringify(results, null, 2));
if (results.some((result) => !result.valid)) process.exitCode = 1;
else console.log(`全部 ${results.length} 个 VMD 通过 Three.js 解析检查`);
