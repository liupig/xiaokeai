/** 抖音弹幕收件箱的前端镜像。舞台和设置看同一份。 */
import { reactive } from 'vue';
import { api, type LiveDanmaku } from '../../api/client';

export const douyinFeed = reactive({
  lines: [] as LiveDanmaku[],
  after: 0,
  listening: false,
  error: '',
  /** 连上后舞台弹幕区默认展开。关掉只藏面板。 */
  open: true,
});

let timer: ReturnType<typeof setInterval> | null = null;

export function resetDouyinFeed() {
  douyinFeed.lines = [];
  douyinFeed.after = 0;
  douyinFeed.error = '';
  douyinFeed.open = true;
}

export function closeDanmakuPanel() {
  douyinFeed.open = false;
}

export function showDanmakuPanel() {
  douyinFeed.open = true;
}

export async function pullDouyinFeed() {
  const data = await api.liveDouyinFeed(douyinFeed.after);
  const was = douyinFeed.listening;
  douyinFeed.listening = !!data.listening;
  douyinFeed.error = data.error || '';
  if (!was && douyinFeed.listening) douyinFeed.open = true;
  if (data.items?.length) {
    douyinFeed.lines = [...douyinFeed.lines, ...data.items].slice(-40);
    douyinFeed.after = data.seq || douyinFeed.after;
  }
}

export function startDouyinFeed() {
  if (timer) return;
  void pullDouyinFeed().catch((e) => {
    douyinFeed.error = String(e);
  });
  timer = setInterval(() => {
    void pullDouyinFeed().catch((e) => {
      douyinFeed.error = String(e);
    });
  }, 1500);
}

export function stopDouyinFeed() {
  if (timer) clearInterval(timer);
  timer = null;
}
