import { BufferAttribute, DynamicDrawUsage, LoaderUtils, type SkinnedMesh } from 'three';
import type { MMDLoader } from 'three-stdlib';

interface PmxElement {
  index: number;
  position: number[];
  ratio: number;
}

interface PmxModel {
  metadata: { vertexCount: number; morphCount: number };
  morphs: { name: string; type: number; elements: PmxElement[] }[];
}

// The loader has already converted PMX vertex offsets to Three's coordinates.
// Apply them before skinning, keeping the same named weights for UI and VMD.
function bindSparseMorphs(mesh: SkinnedMesh, morphs: PmxModel['morphs']) {
  delete mesh.geometry.morphAttributes.position;
  const position = mesh.geometry.getAttribute('position') as BufferAttribute;
  position.setUsage(DynamicDrawUsage);
  const xyz = position.array as Float32Array;
  const rest = xyz.slice();
  const weights = mesh.morphTargetInfluences = Array<number>(morphs.length).fill(0);
  mesh.morphTargetDictionary = Object.fromEntries(morphs.map((m, i) => [m.name, i]));
  const previous = weights.slice();
  const vertices = morphs.map(m => {
    if (m.type !== 1 || !m.elements.length) return undefined;
    let first = Infinity, end = 0;
    for (const { index } of m.elements) {
      first = Math.min(first, index * 3);
      end = Math.max(end, index * 3 + 3);
    }
    return { first, end, offsets: m.elements };
  });
  // MMDLoader supports vertex morphs and groups referring to vertex morphs.
  const channels = morphs.map((m, i) => {
    const direct = vertices[i];
    if (direct) return [{ target: direct, ratio: 1 }];
    if (m.type !== 0) return [];
    return m.elements.flatMap(({ index, ratio }) => {
      const target = vertices[index];
      return target ? [{ target, ratio }] : [];
    });
  });

  return () => {
    if (!weights.some((value, i) => value !== previous[i])) return;
    let first = Infinity, end = 0;
    for (let i = 0; i < weights.length; i++) {
      if (!weights[i] && !previous[i]) continue;
      for (const { target } of channels[i]) {
        first = Math.min(first, target.first);
        end = Math.max(end, target.end);
      }
      previous[i] = weights[i];
    }
    if (end <= first) return;
    xyz.set(rest.subarray(first, end), first);
    for (let i = 0; i < weights.length; i++) {
      if (!weights[i]) continue;
      for (const { target, ratio } of channels[i]) {
        const w = weights[i] * ratio;
        for (const { index, position: delta } of target.offsets) {
          const j = index * 3;
          xyz[j] += delta[0] * w;
          xyz[j + 1] += delta[1] * w;
          xyz[j + 2] += delta[2] * w;
        }
      }
    }
    position.addUpdateRange(first, end - first);
    position.needsUpdate = true;
  };
}

export function loadPreviewPmx(loader: MMDLoader, url: string,
  onLoad: (mesh: SkinnedMesh, updateMorphs?: () => void) => void, onError: (e: unknown) => void) {
  const builder = loader.meshBuilder as {
    setCrossOrigin(value: string): void;
    build(data: PmxModel, texturePath: string, progress: undefined, error: typeof onError): SkinnedMesh;
  };
  builder.setCrossOrigin(loader.crossOrigin);
  loader.loadPMX(url, raw => {
    const data = raw as PmxModel;
    // A dense RGBA32F texture for Yuexiao's 135 morphs exceeds 1.2 GiB.
    // Reserve GPU morphs for smaller meshes. Retain the PMX material morph
    // definitions for the loader's transparency checks in both paths.
    const sparse = data.metadata.vertexCount * data.metadata.morphCount * 16 > 128 * 1024 * 1024;
    const model = sparse ? { ...data, metadata: { ...data.metadata, morphCount: 0 } } : data;
    const mesh = builder.build(model, LoaderUtils.extractUrlBase(url), undefined, onError);
    onLoad(mesh, sparse ? bindSparseMorphs(mesh, data.morphs) : undefined);
  }, undefined, onError);
}
