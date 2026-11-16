import type { Directive } from 'vue';
import { useSettingsStore } from '../../stores/settings';

type Lang = 'en' | 'ja' | 'ko' | 'ru';
const zh = (en: string, ja: string, ko: string, ru: string): Record<Lang, string> => ({ en, ja, ko, ru });

/** Local UI copy. Character-owned memories and reflections are never machine translated. */
const COPY: Record<string, Record<Lang, string>> = {
  '总览': zh('Overview', '総覧', '개요', 'Обзор'), '心意': zh('Gifts', '想い', '마음', 'Чувства'),
  '故事': zh('Story', '物語', '이야기', 'История'), '设置': zh('Settings', '設定', '설정', 'Настройки'),
  '这一刻': zh('This moment', 'この瞬間', '지금 이 순간', 'Этот момент'),
  '我记得': zh('I remember', '覚えている', '기억해', 'Я помню'),
  '我们的习惯': zh('Our rituals', 'ふたりの習慣', '우리의 습관', 'Наши привычки'),
  '长久的故事': zh('A lasting story', '長い物語', '오랜 이야기', 'Долгая история'),
  'AI 陪伴等级': zh('AI companionship', 'AI 陪伴レベル', 'AI 동행 레벨', 'Уровень ИИ'),
  '角色羁绊': zh('Bond', '絆', '유대', 'Связь'), '恋爱好感': zh('Romance', '恋愛好感', '연애 호감', 'Романтика'),
  '内心发现': zh('Inner discoveries', '心の発見', '남면의 발견', 'Внутренние открытия'),
  '下一项期待': zh('Next milestone', '次の楽しみ', '다음 기대', 'Следующая цель'),
  '时光札记': zh('Time journal', '時のノート', '시간의 기록', 'Заметки времени'),
  '最近收获': zh('Recent rewards', '最近の收获', '최근 보상', 'Недавние награды'),
  '去准备一份心意': zh('Prepare a gift', '想いを用意する', '마음 준비하기', 'Подготовить подарок'),
  '已经发现的心里话': zh('Discovered thoughts', '見つけた本音', '발견한 속마음', 'Найденные мысли'),
  '尚未发现的内心片段': zh('Undiscovered inner page', '未発見の心のページ', '미발견 남면', 'Неоткрытая страница'),
  '查看全部内心档案': zh('View all inner pages', '心の記録をすべて見る', '모든 남면 보기', 'Все внутренние записи'),
  '故事的第一页，还等着落笔': zh('The first page is waiting', '物語の最初のページ', '첫 페이지가 기다려요', 'Первая страница ждёт'),
  '留下第一件事': zh('Save a first moment', '最初の出来事を残す', '첫 순간 남기기', 'Сохранить первый момент'),
  '她最近偏爱': zh('Her recent preferences', '彼女の最近の好み', '그녀의 최근 취향', 'Её недавние предпочтения'),
  '听她怎么说': zh('Hear her thoughts', '彼女の話を聞く', '그녀의 이야기 듣기', 'Её слова'),
  '心意套装': zh('Gift collections', '心意セット', '선물 세트', 'Наборы подарков'),
  '她给你的回礼': zh('Her gifts to you', '彼女からの贈り物', '그녀의 답례', 'Её ответные подарки'),
  '礼物图鉴': zh('Gift archive', '贈り物図鑑', '선물 도감', 'Архив подарков'),
  '第一份心意，会有专门的位置': zh('The first gift has a special place', '最初の想いの特別な場所', '첫 마음의 자리', 'Для первого подарка есть место'),
  '我们的共同章节': zh('Our chapters', 'ふたりの章', '우리의 장', 'Наши главы'),
  '待续的话题': zh('To be continued', '続きの話題', '이어갈 이야기', 'Продолжение тем'),
  '记下': zh('Save', '記録', '기록', 'Записать'), '已有下文': zh('Followed up', '続きがあった', '후속 있음', 'Есть продолжение'),
  '删除': zh('Delete', '削除', '삭제', 'Удалить'), '保存近况': zh('Save update', '近況を保存', '근황 저장', 'Сохранить'),
  '关系近况': zh('Where we are', 'ふたりの近況', '우리의 근황', 'Наши отношения сейчас'),
  '共同时光模式': zh('Shared-time mode', '共同时光モード', '공동 시간 모드', 'Режим общего времени'),
  '完整共同时光': zh('Full shared time', '完全な共同时光', '전체 공동 시간', 'Полное общее время'),
  '仅共同回忆': zh('Memories only', '共同の思い出のみ', '추억만', 'Только воспоминания'),
  '固定剧情': zh('Fixed story', '固定ストーリー', '고정 스토리', 'Фиксированный сюжет'),
  '关系表达': zh('Relationship expression', '関係の表現', '관계 표현', 'Выражение отношений'),
  '遵循角色卡': zh('Follow character card', '角色カードに従う', '캐릭터 카드 준수', 'Следовать карточке'),
  '自由心动路线': zh('Free romance path', '自由な恋愛ルート', '자유 연애 루트', 'Свободный романтический путь'),
  '重置共同时光': zh('Reset shared time', '共同时光をリセット', '공동 시간 초기화', 'Сбросить общее время'),
  '重置': zh('Reset', 'リセット', '초기화', 'Сбросить'), '确认重置': zh('Confirm reset', 'リセットを確認', '초기화 확인', 'Подтвердить'),
  '取消': zh('Cancel', 'キャンセル', '취소', 'Отмена'), '关闭': zh('Close', '閉じる', '닫기', 'Закрыть'),
  '累计送出': zh('Total gifted', '累計贈呈', '총 선물', 'Всего подарено'), '最近好感': zh('Latest affection', '最近の好感', '최근 호감', 'Последняя симпатия'),
  '礼物价格': zh('Gift price', '贈り物の価格', '선물 가격', 'Цена подарка'), '最近赠送': zh('Latest gift date', '最近の贈呈日', '최근 선물일', 'Дата последнего'),
  '已拥有': zh('Collected', '所持', '보유', 'Собрано'), '未收集': zh('Not collected', '未所持', '미수집', 'Не собрано'),
  '安静下午': zh('Quiet afternoon', '静かな午後', '조용한 오후', 'Тихий день'),
  '一起创作': zh('Create together', '一緒に創作', '함께 창작', 'Творим вместе'),
  '把心意留下': zh('Keep the feeling', '想いを残す', '마음 남기기', 'Сохранить чувства'),
  '日常新装': zh('Everyday style', '日常の新装', '일상 새 옷', 'Повседневный стиль'),
  '暖意出门': zh('Warm outing', '暖かい外出', '따뜻한 외출', 'Тёплая прогулка'),
  '郑重纪念': zh('A special memory', '特別な記念', '특별한 기념', 'Особая память'),
  '一朵小花': zh('A little flower', '小さな花', '작은 꽃', 'Маленький цветок'),
  '一杯热茶': zh('A cup of tea', '温かいお茶', '따뜻한 차', 'Чашка чая'),
  '窗边读物': zh('Window-side book', '窓辺の本', '창가의 책', 'Книга у окна'),
  '一支画笔': zh('A paintbrush', '一本の筆', '그림 붓', 'Кисть'),
  '手写卡片': zh('Handwritten card', '手書きカード', '손편지', 'Открытка'),
  '共同相册': zh('Shared album', '共同アルバム', '공동 앨범', 'Общий альбом'),
  '窗边风铃': zh('Window chime', '窓辺の風鈴', '창가 풍경', 'Колокольчик'),
  '日常眼镜': zh('Everyday glasses', '日常の眼鏡', '일상 안경', 'Очки'),
  '出门帽子': zh('Outing hat', 'お出かけ帽', '외출 모자', 'Шляпа'),
  '舒适便装': zh('Casual outfit', '普段着', '편한 옷', 'Домашняя одежда'),
  '暖意大衣': zh('Warm coat', '暖かいコート', '따뜻한 코트', 'Тёплое пальто'),
  '纪念礼服': zh('Memorial dress', '記念ドレス', '기념 드레스', 'Праздничное платье'),
  '初识': zh('First meeting', '初対面', '첫 만남', 'Знакомство'), '熟悉': zh('Familiar', '親しくなる', '친숙', 'Близость'),
  '信任': zh('Trust', '信頼', '신뢰', 'Доверие'), '默契': zh('In sync', '阿吽', '교감', 'Понимание'),
  '羁绊': zh('Bonded', '絆', '유대', 'Привязанность'), '知心': zh('Kindred', '知心', '지심', 'Родство'),
  '心动': zh('Spark', 'ときめき', '설렘', 'Трепет'), '靠近': zh('Closer', '近づく', '가까워짐', 'Сближение'),
  '暧昧': zh('Almost lovers', '暧昧', '썸', 'Неопределённость'), '相恋': zh('In love', '恋愛', '사랑', 'Влюблённые'),
  '深爱': zh('Deep love', '深愛', '깊은 사랑', 'Глубокая любовь'),
};

function translate(text: string, lang: string) {
  const normalized = text.replace(/\s+/g, ' ').trim();
  return COPY[normalized]?.[lang as Lang] || text;
}

function localize(el: HTMLElement) {
  const lang = useSettingsStore().locale.ui || 'zh-CN';
  if (lang === 'zh-CN') return;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  for (const node of nodes) {
    const next = translate(node.nodeValue || '', lang);
    if (next !== node.nodeValue) node.nodeValue = next;
  }
  for (const child of [el, ...el.querySelectorAll<HTMLElement>('*')]) {
    for (const name of ['placeholder', 'aria-label']) {
      const value = child.getAttribute(name);
      if (value) child.setAttribute(name, translate(value, lang));
    }
  }
}

export const journeyI18n: Directive<HTMLElement> = {
  mounted: localize,
  updated: localize,
};
