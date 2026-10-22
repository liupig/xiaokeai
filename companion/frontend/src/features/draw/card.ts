import { reactive } from 'vue';
import { useCharacterStore } from '../../stores/character';
import { refreshKeepsakes } from '../keepsake/session';

export const drawnCard = reactive({
  url: '',
  name: '',
  zoom: false,
  waiting: false,
});

async function clearStuckCard() {
  const { tarotUi } = await import('../tarot/session');
  if (tarotUi.phase !== 'off' && tarotUi.phase !== 'leaving') return;
  const { getTarotPlugin } = await import('../tarot/plugin');
  const plugin = getTarotPlugin();
  if (plugin) void plugin.dismiss();
}

/** 出图的这几十秒，牌位先占上，免得屏幕空着。 */
export async function showDrawing(name: string) {
  drawnCard.waiting = true;
  drawnCard.zoom = false;
  drawnCard.url = '';
  drawnCard.name = (name || '').slice(0, 10);
  await clearStuckCard();
}

/** 收掉屏幕上这张牌。相册里的原图还在。 */
export function dismissDrawnCard() {
  drawnCard.waiting = false;
  drawnCard.url = '';
  drawnCard.name = '';
  drawnCard.zoom = false;
}

/** 屏幕右侧、上下居中。不挂在角色身上。 */
export async function showDrawnCard(url: string, name: string) {
  if (!url) {
    drawnCard.waiting = false;
    drawnCard.url = '';
    return;
  }
  drawnCard.waiting = false;
  drawnCard.url = url;
  drawnCard.name = (name || '').slice(0, 10);
  drawnCard.zoom = false;
  const id = useCharacterStore().currentId;
  if (id) void refreshKeepsakes(id);
  await clearStuckCard();
}
