import { MathUtils, type Skeleton } from 'three';

// Follow the head down the existing rig. The knot stays at its bind pose,
// while progressively slower sections carry the turn through to the tips.
export function createLiutingDrape(skeleton: Skeleton) {
  const sections = [
    { names: ['HairTail_03'], rate: 13, strength: 0.44 },
    { names: ['HairTail_08'], rate: 8, strength: 0.53 },
    { names: ['HairTail_13'], rate: 5.5, strength: 0.60 },
  ].map(({ names, rate, strength }) => ({ joints: bind(names), rate, strength, pitch: 0, yaw: 0 }));
  const ties = bind(['HairTail_01']);
  const temples = bind(['左SHair_03', '右SHair_03']);
  let applied = false;

  function bind(names: string[]) {
    return names.flatMap(name => {
      const bone = skeleton.getBoneByName(name);
      return bone ? [{ bone, rest: bone.rotation.clone() }] : [];
    });
  }

  function reset() {
    if (applied) {
      for (const { joints } of sections) for (const { bone, rest } of joints) bone.rotation.copy(rest);
      for (const { bone, rest } of ties) bone.rotation.copy(rest);
      for (const { bone, rest } of temples) bone.rotation.copy(rest);
    }
    applied = false;
  }

  function update(dt: number, pitch: number, yaw: number) {
    let parentPitch = pitch, parentYaw = yaw;
    // The knot turns with the skull, but the suspended length hangs from
    // the tie. Counter the head's tilt here, before lag is distributed
    // down the chain, so a deep nod cannot sweep the lengths into the back.
    for (const {bone, rest} of ties) {
      bone.rotation.set(rest.x - pitch, rest.y - .78*yaw, rest.z, rest.order);
    }
    for (const section of sections) {
      if (!applied) { section.pitch = pitch; section.yaw = yaw; }
      const follow = 1 - Math.exp(-section.rate * dt);
      section.pitch += follow * (parentPitch - section.pitch);
      section.yaw += follow * (parentYaw - section.yaw);
      const bend = MathUtils.clamp((section.pitch-parentPitch)*section.strength*.75, -.012, .075);
      const swing = MathUtils.clamp((section.yaw-parentYaw)*section.strength, -.12, .12);
      for (const {bone, rest} of section.joints) {
        bone.rotation.set(rest.x+bend, rest.y+.32*swing, rest.z+.73*swing, rest.order);
      }
      parentPitch = section.pitch;
      parentYaw = section.yaw;
    }
    for (const {bone, rest} of temples) {
      bone.rotation.set(rest.x+.20*(sections[0].pitch-pitch), rest.y,
                        rest.z+.18*(sections[0].yaw-yaw), rest.order);
    }
    applied = true;
  }
  return { update, reset };
}
