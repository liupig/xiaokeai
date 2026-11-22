export type ExpressionCue = { name: string; weight: number; seconds: number };

export function isPerformanceMorph(name: string) {
  return !/^(?:[あいうえおんアイウエオワ]|aa|ih|ou|ee|oh|[aiueo]|viseme.*|jawopen|mouthopen|まばたき|瞬き|blink(?:left|right)?|eyeblink(?:left|right)?)$/iu.test(name.trim());
}

export function parseExpressionCue(raw: string, supported: readonly string[]): ExpressionCue | null {
  const input = raw.trim();
  const fields = input.split(':');
  let name = input;
  let weight = 0.76;
  let seconds = 2.2;
  const numeric = /^(?:\d+(?:\.\d+)?|\.\d+)$/;
  if (!supported.includes(name)) {
    const last = fields.pop()?.trim() ?? '';
    if (!numeric.test(last)) return null;
    if (fields.length >= 2 && numeric.test(fields[fields.length - 1].trim())) {
      seconds = Number(last);
      weight = Number(fields.pop());
    } else {
      weight = Number(last);
    }
    name = fields.join(':').trim();
  }
  if (!supported.includes(name) || !isPerformanceMorph(name)
    || !Number.isFinite(weight) || !Number.isFinite(seconds) || weight < 0 || weight > 1
    || seconds < 0.3 || seconds > 6) return null;
  return { name, weight, seconds };
}
