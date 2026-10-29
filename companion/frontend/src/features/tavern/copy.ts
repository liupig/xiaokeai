import { cardStyleNow } from './cards';

export interface RevealLine {
  caller: string;
  actor: string;
  cards: string;
  honest: boolean;
  shooter: string;
  hit: boolean;
}

export interface FaceCopy {
  name: string;
  role: string;
  line: string;
}

export interface TavernPack {
  title: string;
  kicker: string;
  rules: string;
  enter: string;
  leave: string;
  again: string;
  truth: string;
  play: string;
  call: string;
  goon: string;
  yourTurn: string;
  first: string;
  nameHint: string;
  wait: string;
  flipTitle: string;
  riteTitle: string;
  think: (who: string, naming: boolean) => string;
  focusPlay: string;
  focusName: string;
  focusCall: string;
  focusRite: string;
  back: string;
  dead: string;
  comma: string;
  err: Record<string, string>;
  face: Record<string, FaceCopy>;
  seat: Record<string, string>;
  sayPlay: (who: string, n: number) => string;
  sayDeal: (face: string, who: string) => string;
  sayRite: (who: string) => string;
  sayName: (who: string, face: string) => string;
  sayClear: (who: string) => string;
  sayWin: (who: string) => string;
  sayReveal: (o: RevealLine) => string;
  sayGun: (who: string, n: number) => string;
  sayClick: (who: string) => string;
  sayShot: (who: string) => string;
  linePlay: (n: number, face: string) => string;
  lineCall: string;
  lineName: (face: string) => string;
  lineDeal: (face: string) => string;
  lineClear: string;
  lineGun: (n: number) => string;
  lineClick: string;
  lineShot: string;
  host: string;
  lineHost: (face: string, who: string) => string;
  board: string;
  played: string;
  wins: string;
  pts: string;
  coinLine: (n: number) => string;
  place: (n: number) => string;
  spentHint: string;
  nextRound: string;
  bye: string;
  aside: string;
  againHint: string;
  lineStill: (names: string, face: string, who: string) => string;
  lineKeep: (names: string, face: string, who: string) => string;
  exitTitle: string;
  exitLine: (who: string) => string;
  triumphTitle: string;
  triumphLine: (who: string, rank: number) => string;
  scoreLine: (tag: string, rank: number, name: string, points: number) => string;
  verb: { play: string; follow: string; call: string; name: string; deal: string; keep: string; clear: string };
}

const FACE_ZH: Record<string, FaceCopy> = {
  loli: { name: '萝莉', role: '真话', line: '浅粉 · 洛丽塔' },
  girl: { name: '少女', role: '真话', line: '晴空 · 黄衣' },
  lady: { name: '御姐', role: '真话', line: '冷色 · 高领' },
  pup: { name: '犬系', role: '真话', line: '软毛 · 针织' },
  boy: { name: '正太', role: '真话', line: '短发 · 外套' },
  sire: { name: '爹系', role: '真话', line: '大衣 · 沉稳' },
  mei: { name: '魅', role: '大王', line: '馆主 · 出什么都算真话' },
  ying: { name: '影', role: '小王', line: '侍者 · 出什么都算真话' },
};

const ZH: TavernPack = {
  title: '魅影酒馆',
  kicker: '骗子酒馆',
  rules: '二十张牌。入座前可选牌组和画风。一副是萝莉、少女、御姐，另一副是犬系、正太、爹系，各六张。出牌按逆时针，KE 的下家在右边。第一轮由系统随机指定桌牌和先手。打出去的牌离开手牌。手里出完就轮空，不会补牌。场上只剩两个人时，上家打出最后一手，下家必须揭穿，不能再出牌。有人中弹离席也不发牌，没打完的人继续打剩下的牌。只有还坐着的人自己把牌打光，才重新发。先出完的人不再回到最后两人的新局，离席的也不会回来。XiaO、AI 和她会自己想这一手是揭穿还是跟牌，并且把这句说出来。被揭穿之后，先进仪式。空膛就继续坐着，并由这个人指定下一轮牌型；手里还有牌，就再出一到三张。实弹就离席。魅和影都算这张桌牌。每人三膛一颗实弹。最后两个人里有一个出完牌，仪式裁决完，就只在这两个人之间重发，不再单人把剩下的牌打完。提前出完的人按先后加 50、20、10 分。离席的人按先后扣 50、30、10 分。最后活下来的人，和提前出完的人，都算胜利。',
  enter: '入座',
  leave: '离桌',
  again: '再坐一局',
  truth: '本轮桌牌',
  play: '出牌',
  call: '揭穿',
  goon: '继续',
  yourTurn: '轮到你。可以跟牌，也可以揭穿上一手。',
  first: '你先手。这一轮还没有能揭穿的牌。',
  nameHint: '仪式结束。由你指定这一轮的桌牌。手里还有牌就接着出，出完了这一轮就轮空。',
  wait: '别人在想。',
  flipTitle: '揭穿',
  riteTitle: '仪式',
  think: (who, naming) => (naming ? `${who}在定这一轮的牌型。` : `${who}在看牌，决定要揭穿还是跟。`),
  focusPlay: '出牌',
  focusName: '定牌',
  focusCall: '揭穿',
  focusRite: '仪式',
  back: '牌背',
  dead: '已离席',
  comma: '、',
  err: {
    count: '一次出一到三张。',
    missing: '手里没有这张牌。',
    turn: '还没轮到你。',
    nocall: '还没有可以揭穿的牌。',
    wait: '等这一手翻完。',
    off: '魅影酒馆没开。',
    idle: '还没入座。',
    empty: '没有牌可出。',
    face: '桌牌只能是这一副里的三种。',
    spent: '这轮没有牌了。',
  },
  face: FACE_ZH,
  seat: { you: 'KE', qin: 'XiaO', bar: 'AI', her: '她' },
  sayPlay: (who, n) => `${who}扣下 ${n} 张。`,
  sayDeal: (face, who) => `系统指定本轮桌牌：${face}。先手是${who}。`,
  sayRite: (who) => `${who}仪式结束。这一轮的牌型和张数由${who}来定。`,
  sayName: (who, face) => `${who}指定本轮桌牌：${face}。`,
  sayClear: (who) => `${who}把手里的牌出完了，没人揭穿。`,
  sayWin: (who) => `${who}赢下这一夜。`,
  sayReveal: (o) => `${o.caller}揭开了${o.actor}扣下的牌：${o.cards}。${o.honest ? '全是这轮桌牌，揭穿没有成。' : '里面有别的脸，揭穿成了。'}`,
  sayGun: (who, n) => `${who}把枪转向自己。三膛里有一颗实弹，现在扣的是第${n}膛。`,
  sayClick: (who) => `空膛。${who}还坐着。下一轮的牌型，由${who}来定。`,
  sayShot: (who) => `实弹。${who}离席。下一轮的桌牌改由系统指定。`,
  linePlay: (n, face) => `我跟。${['', '一', '两', '三'][n] || n}张${face}。`,
  lineCall: '揭穿。我不信。',
  lineName: (face) => `这一轮，${face}。`,
  lineDeal: (face) => `这一轮是${face}。我先来。`,
  lineClear: '我出完了。',
  lineGun: (n) => `第${n}膛。`,
  lineClick: '空的。我还在。',
  lineShot: '中了。',
  host: '主持',
  lineHost: (face, who) => `本轮桌牌，${face}。先手，${who}。`,
  board: '战绩',
  played: '场',
  wins: '胜',
  pts: '分',
  coinLine: (n) => (n > 0 ? `金币 +${n}` : `金币 ${n}`),
  place: (n) => ['', '第一', '第二', '第三', '垫底'][n] || String(n),
  spentHint: '这一轮牌都出完了。下一轮只发给还坐着的人，离席的不会回来。',
  nextRound: '开下一轮',
  bye: '轮空',
  aside: '已出完',
  againHint: '再坐一局是四个人重新开一夜。这一轮还没结束的话，离席的人不会被发回来。',
  lineStill: (names, face, who) => `还坐着的是${names}。只发给他们。本轮桌牌，${face}。先手，${who}。`,
  lineKeep: (names, face, who) => `牌不重发。还坐着的是${names}。这一轮桌牌，${face}。轮到${who}。`,
  exitTitle: '退场',
  exitLine: (who) => `${who}中弹，离席。`,
  triumphTitle: '出完',
  triumphLine: (who, rank) => (rank <= 1 ? `${who}先出完。这一夜，先走的人有光。` : `${who}也出完了。`),
  scoreLine: (tag, rank, name, points) => {
    const mark = points > 0 ? `+${points}` : String(points);
    const finish = ['', '先出完', '第二个出完', '第三个出完'][rank] || '出完';
    const death = ['', '先离席', '第二离席', '第三离席'][rank] || '离席';
    if (tag === 'win') return `胜利 ${name}`;
    if (tag === 'finish') return `胜利 ${finish} ${name} ${mark}`;
    if (tag === 'death') return `${death} ${name} ${mark}`;
    return `${name} ${mark}`;
  },
  verb: { play: '出牌', follow: '跟', call: '揭穿', name: '定牌', deal: '开局', keep: '续打', clear: '出完' },
};

const EN: TavernPack = {
  title: 'Phantom Tavern',
  kicker: "Liar's table",
  rules: 'Twenty cards. Before you sit, pick a deck and an art style. One deck is Lolita, Maiden, and Lady. The other is Puppy, Boyish, and Daddy. Six of each. One suit is the truth this round. Charm is the high joker, Shade the low joker, and both are wild. Play one to three cards face down and claim they all match the center. The next player follows, or calls the bluff. A false call takes the gun; a true one hands it to the accuser. Three chambers, one bullet. Early finishers score +50, +20, +10 in that order. The dead score −50, −30, −10 in that order. The last one alive, and anyone who already finished, all count as winners.',
  enter: 'Sit down',
  leave: 'Leave',
  again: 'Another night',
  truth: 'Table card',
  play: 'Play',
  call: 'Call',
  goon: 'Continue',
  yourTurn: 'Your turn. Follow, or call the last play.',
  first: 'You open. Nothing to call yet.',
  nameHint: 'The rite is over. Name this round’s card, then play one to three.',
  wait: 'Someone else is thinking.',
  flipTitle: 'Called',
  riteTitle: 'The rite',
  think: (who, naming) => (naming ? `${who} is choosing the card.` : `${who} is deciding whether to call or follow.`),
  focusPlay: 'Play',
  focusName: 'Name',
  focusCall: 'Call',
  focusRite: 'Rite',
  back: 'Back',
  dead: 'Out',
  comma: ', ',
  err: {
    count: 'Play one to three cards.',
    missing: 'That card is not in your hand.',
    turn: 'Not your turn.',
    nocall: 'Nothing to call yet.',
    wait: 'Wait for this reveal.',
    off: 'Phantom Tavern is off.',
    idle: 'No one is seated.',
    empty: 'No card to play.',
    face: 'The table card must be one of this deck\'s three suits.',
  },
  face: {
    loli: { name: 'Lolita', role: 'Truth', line: 'Pale pink, full dress' },
    girl: { name: 'Maiden', role: 'Truth', line: 'Bright and in motion' },
    lady: { name: 'Lady', role: 'Truth', line: 'Cold, and fully composed' },
    pup: { name: 'Puppy', role: 'Truth', line: 'Soft eyes, knit sweater' },
    boy: { name: 'Boyish', role: 'Truth', line: 'Short hair, buttoned coat' },
    sire: { name: 'Daddy', role: 'Truth', line: 'Calm, in a tailored coat' },
    mei: { name: 'Charm', role: 'High', line: 'The mistress. Always truth.' },
    ying: { name: 'Shade', role: 'Low', line: 'The attendant. Always truth.' },
  },
  seat: { you: 'KE', qin: 'XiaO', bar: 'AI', her: 'Her' },
  sayPlay: (who, n) => `${who} plays ${n}.`,
  sayDeal: (face, who) => `The house names ${face}. ${who} opens.`,
  sayRite: (who) => `${who} finishes the rite and names the next card.`,
  sayName: (who, face) => `${who} names ${face}.`,
  sayClear: (who) => `${who} emptied a hand, and nobody called.`,
  sayWin: (who) => `${who} takes the night.`,
  sayReveal: (o) => `${o.caller} turns over ${o.actor}'s cards: ${o.cards}. ${o.honest ? 'All of them match. The call fails.' : 'Another face is in there. The call lands.'}`,
  sayGun: (who, n) => `${who} turns the gun on themselves. One bullet in three. This is chamber ${n}.`,
  sayClick: (who) => `Empty. ${who} stays. ${who} names the next card.`,
  sayShot: (who) => `The bullet. ${who} leaves. The house names the next card.`,
  linePlay: (n, face) => (n === 1 ? `I follow. One ${face}.` : `I follow. ${n} ${face}.`),
  lineCall: "I call. I don't believe you.",
  lineName: (face) => `This round: ${face}.`,
  lineDeal: (face) => `This round is ${face}. I'll open.`,
  lineClear: "That's the last of mine.",
  lineGun: (n) => `Chamber ${n}.`,
  lineClick: "Empty. I'm still here.",
  lineShot: "It hit.",
  host: 'Host',
  lineHost: (face, who) => `Table card, ${face}. ${who} opens.`,
  board: 'Record',
  played: 'played',
  wins: 'won',
  pts: 'pts',
  coinLine: (n) => (n > 0 ? `coins +${n}` : `coins ${n}`),
  place: (n) => ['', '1st', '2nd', '3rd', 'last'][n] || String(n),
  spentHint: 'This round is empty. The next deal goes only to whoever is still seated.',
  nextRound: 'Next round',
  bye: 'Passed',
  aside: 'Finished',
  againHint: 'Another night seats all four again. A round still going only deals to whoever is still seated.',
  lineStill: (names, face, who) => `Still seated: ${names}. Deal only to them. Table card, ${face}. ${who} opens.`,
  lineKeep: (names, face, who) => `No redeal. Still seated: ${names}. Table card, ${face}. ${who}'s turn.`,
  exitTitle: 'Exit',
  exitLine: (who) => `${who} is hit, and leaves.`,
  triumphTitle: 'Finished',
  triumphLine: (who, rank) => (rank <= 1 ? `${who} finishes first.` : `${who} finishes too.`),
  scoreLine: (tag, rank, name, points) => {
    const mark = points > 0 ? `+${points}` : String(points);
    if (tag === 'win') return `Victory ${name}`;
    if (tag === 'finish') return `Victory ${['', 'first out', 'second out', 'third out'][rank] || 'out'} ${name} ${mark}`;
    if (tag === 'death') return `${['', 'First down', 'Second down', 'Third down'][rank] || 'Down'} ${name} ${mark}`;
    return `${name} ${mark}`;
  },
  verb: { play: 'Play', follow: 'Follow', call: 'Call', name: 'Name', deal: 'Deal', keep: 'Continue', clear: 'Empty' },
};

const JA: TavernPack = {
  title: '魅影酒場',
  kicker: 'ライアーズバー',
  rules: '二十枚。着席前に牌組と画風を選ぶ。一組はロリータ・少女・御姉、もう一組は犬系・ショタ・パパ系。各六枚で、そのどれかがこの回の真実。魅は大王、影は小王、どちらも万能。一から三枚を伏せて、全部それだと宣言する。次の人は続くか、嘘を暴く。外れれば暴いた人が銃、本当なら出した人が銃。三室に一発。先に出し切った順に +50、+20、+10。倒れた順に −50、−30、−10。最後に残った人が勝つ。',
  enter: '着席',
  leave: '立席',
  again: 'もう一局',
  truth: 'この回の卓札',
  play: '出す',
  call: '暴く',
  goon: '続ける',
  yourTurn: 'あなたの番。続けるか、前の手を暴く。',
  first: 'あなたが先手。まだ暴く手がない。',
  nameHint: '儀式が終わった。この回の卓札を決め、一枚から三枚出す。',
  wait: '誰かが考えている。',
  flipTitle: '暴露',
  riteTitle: '儀式',
  think: (who, naming) => (naming ? `${who}がこの回の卓札を決めている。` : `${who}が暴くか、出すか考えている。`),
  focusPlay: '出す',
  focusName: '指定',
  focusCall: '暴く',
  focusRite: '儀式',
  back: '裏',
  dead: '退席',
  comma: '、',
  err: {
    count: '一枚から三枚。',
    missing: 'その札は手にない。',
    turn: 'まだあなたの番ではない。',
    nocall: '暴く札がまだない。',
    wait: 'この開示を待つ。',
    off: '魅影酒場はオフ。',
    idle: 'まだ着席していない。',
    empty: '出せる札がない。',
    face: '卓札はその三種類だけ。',
  },
  face: {
    loli: { name: 'ロリータ', role: '真実', line: '淡いピンクのドレス' },
    girl: { name: '少女', role: '真実', line: '明るく、動いている' },
    lady: { name: '御姉', role: '真実', line: '冷たく、整っている' },
    pup: { name: '犬系', role: '真実', line: 'やわらかい目、ニット' },
    boy: { name: 'ショタ', role: '真実', line: '短髪、コート' },
    sire: { name: 'パパ系', role: '真実', line: '落ち着いた外套' },
    mei: { name: '魅', role: '大王', line: '女主人。いつも真実' },
    ying: { name: '影', role: '小王', line: '給仕。いつも真実' },
  },
  seat: { you: 'KE', qin: 'XiaO', bar: 'AI', her: '彼女' },
  sayPlay: (who, n) => `${who}が ${n} 枚伏せた。`,
  sayDeal: (face, who) => `場が卓札を${face}に指定。先手は${who}。`,
  sayRite: (who) => `${who}の儀式が終わり、次の卓札は${who}が決める。`,
  sayName: (who, face) => `${who}が卓札を${face}に指定。`,
  sayClear: (who) => `${who}が手札を出し切り、誰も暴かなかった。`,
  sayWin: (who) => `${who}がこの夜を取った。`,
  sayReveal: (o) => `${o.caller}が${o.actor}の札を開いた：${o.cards}。${o.honest ? '全部本当で、暴きは外れた。' : '別の顔があり、暴きは当たった。'}`,
  sayGun: (who, n) => `${who}が自分に銃を向ける。三室に一発。今は${n}室目。`,
  sayClick: (who) => `空鉄。${who}は残る。次の卓札は${who}が決める。`,
  sayShot: (who) => `実弾。${who}は退席。次の卓札は場が決める。`,
  linePlay: (n, face) => `ついて出す。${face}を${n}枚。`,
  lineCall: '暴く。信じない。',
  lineName: (face) => `この回は${face}。`,
  lineDeal: (face) => `この回は${face}。先に出す。`,
  lineClear: '出し切った。',
  lineGun: (n) => `${n}室目。`,
  lineClick: '空だった。まだいる。',
  lineShot: '当たった。',
  host: '司会',
  lineHost: (face, who) => `この回の卓札は${face}。先手は${who}。`,
  board: '成績',
  played: '局',
  wins: '勝',
  pts: '点',
  coinLine: (n) => (n > 0 ? `コイン +${n}` : `コイン ${n}`),
  place: (n) => ['', '1位', '2位', '3位', '最下位'][n] || String(n),
  spentHint: 'この回は空。次の配りはまだ座っている人だけ。',
  nextRound: '次を配る',
  bye: 'パス',
  aside: '出し切り',
  againHint: 'もう一局は四人で最初から。続いている回は、残っている人だけに配る。',
  lineStill: (names, face, who) => `まだ座っているのは${names}。配るのはこの人だけ。卓札は${face}。先手は${who}。`,
  lineKeep: (names, face, who) => `配り直さない。まだ座っているのは${names}。卓札は${face}。${who}の番。`,
  exitTitle: '退場',
  exitLine: (who) => `${who}は被弾して退場。`,
  triumphTitle: '出し切り',
  triumphLine: (who, rank) => (rank <= 1 ? `${who}が先に出し切った。` : `${who}も出し切った。`),
  scoreLine: (tag, rank, name, points) => {
    const mark = points > 0 ? `+${points}` : String(points);
    if (tag === 'win') return `勝利 ${name}`;
    if (tag === 'finish') return `勝利 ${['', '先に出し切り', '二人目', '三人目'][rank] || '出し切り'} ${name} ${mark}`;
    if (tag === 'death') return `${['', '先に退場', '二人目の退場', '三人目の退場'][rank] || '退場'} ${name} ${mark}`;
    return `${name} ${mark}`;
  },
  verb: { play: '出す', follow: '追随', call: '暴く', name: '指定', deal: '開局', keep: '続行', clear: '出し切り' },
};

const KO: TavernPack = {
  title: '환영 주점',
  kicker: '라이어 테이블',
  rules: '스무 장. 앉기 전에 패 묶음과 화풍을 고른다. 한 묶음은 로리타, 소녀, 누님. 다른 묶음은 강아지상, 보이시, 아빠상. 각각 여섯 장이고, 그중 하나가 이번 판의 진실이다. 매는 대왕, 영은 소왕, 둘 다 와일드. 한 장에서 세 장을 엎고 전부 그것이라고 말한다. 다음 사람은 잇거나 들통낸다. 틀리면 들통낸 사람이 총을, 맞으면 낸 사람이 총을 쥔다. 세 칸에 한 발. 먼저 다 낸 순서대로 +50, +20, +10. 쓰러진 순서대로 −50, −30, −10. 마지막까지 앉은 사람이 이긴다.',
  enter: '앉기',
  leave: '일어나기',
  again: '한 판 더',
  truth: '이번 패',
  play: '내기',
  call: '들통',
  goon: '계속',
  yourTurn: '당신 차례. 잇거나, 앞 패를 들통낸다.',
  first: '당신이 먼저. 아직 들통낼 패가 없다.',
  nameHint: '의식이 끝났다. 이번 패를 정하고 한 장에서 세 장을 낸다.',
  wait: '다른 사람이 생각하는 중.',
  flipTitle: '들춤',
  riteTitle: '의식',
  think: (who, naming) => (naming ? `${who}가 이번 패를 정하는 중이다.` : `${who}가 들통낼지 따라낼지 보는 중이다.`),
  focusPlay: '내기',
  focusName: '지정',
  focusCall: '들춤',
  focusRite: '의식',
  back: '뒷면',
  dead: '퇴장',
  comma: ', ',
  err: {
    count: '한 장에서 세 장.',
    missing: '손에 없는 패다.',
    turn: '아직 당신 차례가 아니다.',
    nocall: '들통낼 패가 없다.',
    wait: '이번 공개를 기다린다.',
    off: '환영 주점이 꺼져 있다.',
    idle: '아직 앉지 않았다.',
    empty: '낼 패가 없다.',
    face: '패는 세 가지 중에서만 고른다.',
  },
  face: {
    loli: { name: '로리타', role: '진실', line: '옅은 분홍 드레스' },
    girl: { name: '소녀', role: '진실', line: '밝고 움직인다' },
    lady: { name: '누님', role: '진실', line: '차갑고 단정하다' },
    pup: { name: '강아지상', role: '진실', line: '부드러운 눈, 니트' },
    boy: { name: '보이시', role: '진실', line: '단정한 코트' },
    sire: { name: '아빠상', role: '진실', line: '차분한 외투' },
    mei: { name: '매', role: '대왕', line: '주인. 언제나 진실' },
    ying: { name: '영', role: '소왕', line: '시중. 언제나 진실' },
  },
  seat: { you: 'KE', qin: 'XiaO', bar: 'AI', her: '그녀' },
  sayPlay: (who, n) => `${who}가 ${n}장을 엎었다.`,
  sayDeal: (face, who) => `시스템이 ${face}를 지정. ${who}가 먼저.`,
  sayRite: (who) => `${who}의 의식이 끝났다. 다음 패는 ${who}가 정한다.`,
  sayName: (who, face) => `${who}가 ${face}를 지정.`,
  sayClear: (who) => `${who}가 패를 비웠고, 아무도 들통내지 않았다.`,
  sayWin: (who) => `${who}가 이 밤을 가져갔다.`,
  sayReveal: (o) => `${o.caller}가 ${o.actor}의 패를 뒤집었다: ${o.cards}. ${o.honest ? '전부 맞아, 들춤은 실패다.' : '다른 패가 있어, 들춤은 맞았다.'}`,
  sayGun: (who, n) => `${who}가 총을 스스로에게 돌린다. 세 칸에 한 발. 지금은 ${n}번째 칸.`,
  sayClick: (who) => `빈 격발. ${who}는 남는다. 다음 패는 ${who}가 정한다.`,
  sayShot: (who) => `실탄. ${who}는 나간다. 다음 패는 시스템이 정한다.`,
  linePlay: (n, face) => `따라. ${face} ${n}장.`,
  lineCall: '들통. 안 믿어.',
  lineName: (face) => `이번 판은 ${face}.`,
  lineDeal: (face) => `이번 판은 ${face}. 내가 먼저.`,
  lineClear: '다 냈다.',
  lineGun: (n) => `${n}번째 약실.`,
  lineClick: '빈 약실. 아직 앉아 있어.',
  lineShot: '맞았다.',
  host: '사회',
  lineHost: (face, who) => `이번 패는 ${face}. ${who}가 먼저.`,
  board: '전적',
  played: '판',
  wins: '승',
  pts: '점',
  coinLine: (n) => (n > 0 ? `코인 +${n}` : `코인 ${n}`),
  place: (n) => ['', '1위', '2위', '3위', '꼴찌'][n] || String(n),
  spentHint: '이번 판은 비었다. 다음 패는 아직 앉아 있는 사람에게만 준다.',
  nextRound: '다음 판',
  bye: '쉼',
  aside: '소진',
  againHint: '다시 앉으면 네 명이 처음부터다. 아직 안 끝난 판은 남아 있는 사람에게만 준다.',
  lineStill: (names, face, who) => `아직 앉은 사람은 ${names}. 이 사람들에게만 준다. 패는 ${face}. ${who}가 먼저.`,
  lineKeep: (names, face, who) => `다시 나누지 않는다. 아직 앉은 사람은 ${names}. 패는 ${face}. ${who} 차례.`,
  exitTitle: '퇴장',
  exitLine: (who) => `${who}이 맞고 퇴장한다.`,
  triumphTitle: '소진',
  triumphLine: (who, rank) => (rank <= 1 ? `${who}이 먼저 다 냈다.` : `${who}도 다 냈다.`),
  scoreLine: (tag, rank, name, points) => {
    const mark = points > 0 ? `+${points}` : String(points);
    if (tag === 'win') return `승리 ${name}`;
    if (tag === 'finish') return `승리 ${['', '먼저 소진', '둘째', '셋째'][rank] || '소진'} ${name} ${mark}`;
    if (tag === 'death') return `${['', '먼저 퇴장', '둘째 퇴장', '셋째 퇴장'][rank] || '퇴장'} ${name} ${mark}`;
    return `${name} ${mark}`;
  },
  verb: { play: '냄', follow: '따라', call: '들통', name: '지정', deal: '시작', keep: '이어', clear: '소진' },
};

const PACKS: Record<string, TavernPack> = { 'zh-CN': ZH, en: EN, ja: JA, ko: KO };

export function packOf(lang: string): TavernPack {
  return PACKS[lang] || ZH;
}

export const FACES = ['loli', 'girl', 'lady', 'pup', 'boy', 'sire', 'mei', 'ying'] as const;

const ART_FACE = new Set<string>([...FACES, 'back']);

export function artUrl(id: string): string {
  const face = !id || id === 'back' ? 'back' : id.split(':')[0];
  const file = ART_FACE.has(face) ? face : 'back';
  return `/assets/tavern/cards/${cardStyleNow()}/${file}.jpg?v=4`;
}
