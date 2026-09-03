/** 后台记的是本地墙钟。同一天只显示时分秒。 */
export function friendlyWhen(when?: string, iso?: string) {
  const raw = (when || '').trim();
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(raw)) {
    const now = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    const today = `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
    const [d, t] = raw.split(' ');
    if (d === today) return t;
    const [, m, day] = d.split('-');
    return `${Number(m)}月${Number(day)}日 ${t}`;
  }
  if (!iso) return raw;
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return raw;
  const p = (n: number) => String(n).padStart(2, '0');
  const t = `${p(dt.getHours())}:${p(dt.getMinutes())}:${p(dt.getSeconds())}`;
  const now = new Date();
  if (dt.toDateString() === now.toDateString()) return t;
  return `${dt.getMonth() + 1}月${dt.getDate()}日 ${t}`;
}
