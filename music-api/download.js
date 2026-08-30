#!/usr/bin/env node
/**
 * 命令行歌曲下载工具 —— 数据源: 爱听音乐网 (2t58.com)
 *
 * 用法:
 *   node download.js <歌曲id> [歌曲id...]        按 id 下载
 *   node download.js -s "关键词"                 搜索后下载第 1 首
 *   node download.js -s "关键词" -n 5            搜索后下载前 5 首
 *   node download.js -s "关键词" --all           下载该页全部结果
 *
 * 选项:
 *   -o, --out <目录>    保存目录(默认 ./downloads)
 *   -s, --search <词>   按关键词搜索
 *   -n, --num <数量>    搜索时下载前 N 首(默认 1)
 *       --all           搜索时下载整页结果
 *       --lrc           同时保存 .lrc 歌词
 *   -h, --help          显示帮助
 */
'use strict';

const path = require('path');
const { TwoT58Client } = require('./lib/twot58');

function parseArgs(argv) {
  const opt = { out: 'downloads', num: 1, all: false, lrc: false, search: null, ids: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-o' || a === '--out') opt.out = argv[++i];
    else if (a === '-s' || a === '--search') opt.search = argv[++i];
    else if (a === '-n' || a === '--num') opt.num = Number(argv[++i]) || 1;
    else if (a === '--all') opt.all = true;
    else if (a === '--lrc') opt.lrc = true;
    else if (a === '-h' || a === '--help') opt.help = true;
    else opt.ids.push(a);
  }
  return opt;
}

function bar(received, total) {
  if (!total) return `${(received / 1048576).toFixed(2) } MB`;
  const pct = received / total;
  const width = 24;
  const filled = Math.round(pct * width);
  return `[${'#'.repeat(filled)}${'-'.repeat(width - filled)}] ${(pct * 100).toFixed(0)}% ` +
    `${(received / 1048576).toFixed(2)}/${(total / 1048576).toFixed(2)} MB`;
}

async function main() {
  const opt = parseArgs(process.argv.slice(2));
  if (opt.help || (!opt.search && opt.ids.length === 0)) {
    console.log(require('fs').readFileSync(__filename, 'utf8').match(/\/\*\*[\s\S]*?\*\//)[0]);
    return;
  }

  const client = new TwoT58Client();
  const outDir = path.resolve(opt.out);
  let ids = opt.ids;

  if (opt.search) {
    process.stdout.write(`搜索 "${opt.search}" ...\n`);
    const { songs, total } = await client.search(opt.search);
    if (!songs.length) {
      console.error('没有搜到结果(部分版权敏感词会被站方屏蔽,换个关键词试试)');
      process.exit(1);
    }
    const take = opt.all ? songs.length : Math.min(opt.num, songs.length);
    console.log(`共 ${total} 条结果,将下载前 ${take} 首:`);
    songs.slice(0, take).forEach((s, i) => console.log(`  ${i + 1}. ${s.title}  [${s.id}]`));
    ids = songs.slice(0, take).map((s) => s.id);
  }

  let ok = 0;
  for (const id of ids) {
    try {
      let lastLine = '';
      const result = await client.download(id, outDir, {
        withLyric: opt.lrc,
        onProgress: ({ received, total }) => {
          const line = `  ↓ ${bar(received, total)}`;
          if (line !== lastLine) {
            process.stdout.write('\r' + line.padEnd(60));
            lastLine = line;
          }
        },
      });
      process.stdout.write('\r' + ' '.repeat(62) + '\r');
      console.log(`✔ ${result.title}  →  ${path.relative(process.cwd(), result.file)}` +
        (result.lyricFile ? ' (+lrc)' : ''));
      ok++;
    } catch (e) {
      console.error(`x ${id} 下载失败: ${e.message}`);
    }
  }
  console.log(`\n完成: ${ok}/${ids.length} 首,保存在 ${outDir}`);
}

main().catch((e) => {
  console.error('出错:', e.message);
  process.exit(1);
});
