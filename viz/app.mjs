// The page: the election list, the animated chart and its controls, the popup, and video recording.
import { EPS, fmt, lines, cells, count, parseElection } from './count.mjs';

const ROOT = '../';   // paths in elections.csv are relative to the repo root
// Party colours. Every other label, independents included, takes the independents' teal.
const PARTY_COLORS = { Lab: '#e32636', Con: '#0f4d92', LD: '#ff9933', Gr: '#4cbb17', SNP: '#ffe135', Ind: '#008b8b' };
const colourGroup = p => p in PARTY_COLORS ? p : 'Ind';
// mix a #rrggbb colour with white: t = 0 keeps it, t = 1 is white
const shade = (hex, t) => `rgb(${[1, 3, 5].map(i => Math.round(parseInt(hex.slice(i, i + 2), 16) * (1 - t) + 255 * t))})`;
const $ = id => document.getElementById(id);
const tpl = id => $(id).content.firstElementChild.cloneNode(true);
const speed = () => +$('speed').value;
const sleep = ms => new Promise(r => setTimeout(r, ms / speed()));   // animation time, scaled by the speed menu
const get = url => fetch(url).then(r => { if (!r.ok) throw Error(`${url}: HTTP ${r.status}`); return r.text(); });

const elections = new Map();
let run = 0, current, paused = false, waiting = null, reorder = () => {}, shown = 0;   // shown: the step on screen
let tipInfo = () => null, tipAt = -1;   // the popup's content for a row, and the row it shows

// the pause between steps: the usual wait while playing; while paused, until Play or Next step
const hold = ms => new Promise(resolve => {
  const me = { go: () => { clearTimeout(t); if (waiting == me) waiting = null; resolve(); }, stop: () => clearTimeout(t) };
  const t = paused ? null : setTimeout(me.go, ms / speed());
  waiting = me;
});
const setPaused = p => { paused = p; $('pause').textContent = p ? 'Play' : 'Pause'; };

// Play a count from the start, or jump straight to step `start` and play on from there.
async function show({ e, names, parties, ballots }, start = 0) {
  const me = ++run;
  const { quota, stages } = count(names, e.seats, ballots);
  const votes = stages.map(s => s.votes);
  const T = names.length;   // index of the non-transferable row, after the candidates
  let stage = 0;   // the step on screen, for the first-preference breakdowns
  const lost = stages.reduce((t, s) => t + (s.lost > EPS ? s.lost : 0), 0);
  const max = Math.max(quota, lost, ...votes.flat()) * 1.1;
  const pct = v => v / max * 100 + '%';
  // party colour, lighter for each later candidate sharing it, in ballot order (alphabetical by
  // surname), so the first is darkest
  const groups = parties.map(colourGroup);
  const colors = groups.map((p, i) => {
    const same = groups.flatMap((q, j) => q == p ? [j] : []);
    return shade(PARTY_COLORS[p], same.indexOf(i) / same.length * 0.7);
  });
  const color = i => colors[i];
  // every bar is its votes by the voters' first choice; the last row collects the lost votes
  const comp = i => i == T ? stages[stage].lostSoFar : stages[stage].byFirst[i];
  const total = m => [...m.values()].reduce((a, b) => a + b, 0);
  const order = [...names.map((_, i) => [i]), []];   // each bar's first choices, in the order they arrived
  const rows = names.map((name, i) => {
    const row = tpl('row');
    row.querySelector('.name span').textContent = name;
    row.querySelector('.name small').textContent = parties[i];
    row.querySelector('.dot').style.setProperty('--c', color(i));
    return row;
  });
  rows.push(tpl('row'));
  rows[T].querySelector('.name span').textContent = 'Non-transferable';
  rows.forEach((row, i) => row.dataset.i = i);
  hideTip();
  $('heading').textContent = `${e.council} ${e.year}: ${e.ward}`;
  $('sub').textContent = `${e.seats} seats, ${names.length} candidates, quota ${quota}`;
  $('quota').style.left = pct(quota);
  $('quota').firstChild.textContent = `quota ${quota}`;
  const first = votes[0], bloc = p => names.reduce((t, _, j) => t + (parties[j] == p ? first[j] : 0), 0);
  const sorts = {
    alpha: (a, b) => a - b,   // ballot order, which is alphabetical by surname
    first: (a, b) => first[b] - first[a],
    party: (a, b) => bloc(parties[b]) - bloc(parties[a]) || parties[a].localeCompare(parties[b]) || first[b] - first[a],
  };
  reorder = () => $('rows').replaceChildren(...names.map((_, i) => i).sort(sorts[$('sort').value]).map(i => rows[i]), rows[T]);
  reorder();
  $('chart').querySelectorAll('.chip').forEach(c => c.remove());   // left over from an interrupted run
  const steps = stages.map((s, i) => Object.assign(document.createElement('li'), {
    textContent: `${i + 1}. ${s.note}`, onclick: () => { setPaused(true); show(current, i); },
  }));
  $('steps').replaceChildren(...steps);
  $('view').hidden = false;

  // the popup for a row: its votes by the voters' first choice, largest first
  tipInfo = i => {
    const by = comp(i), x = total(by), head = i == T ? 'Non-transferable' : names[i], party = i == T ? '' : parties[i];
    if (x <= EPS) return { head, party, sub: i == T ? 'No votes lost yet' : 'Eliminated', rows: [] };
    const list = [...by].filter(([, v]) => v > EPS).sort((a, b) => b[1] - a[1]);
    return { head, party, votes: `${fmt(x)} votes`, sub: i == T ? "Lost, by the voters' first choice" : "By the voters' first choice",
      rows: list.map(([o, v]) => ({ color: color(o), who: o == i ? 'Own first preferences' : names[o], party: o == i ? '' : parties[o], votes: fmt(v), share: v / x < 0.0005 ? '<0.1%' : `${(v / x * 100).toFixed(1)}%` })) };
  };
  const paint = (i, st) => {
    const by = comp(i);
    for (const o of by.keys()) if (!order[i].includes(o)) order[i].push(o);   // new first choices join the end
    // a winner's bar is one colour, so draw it as one box: no seams between chunks
    const parts = st == 'elected' ? [[i, total(by)]] : order[i].map(o => [o, by.get(o) ?? 0]).filter(([, v]) => v > EPS);
    let x = 0;
    rows[i].className = 'row ' + st;
    rows[i].querySelector('.track').replaceChildren(...parts.map(([o, v]) => {
      const d = document.createElement('div');
      d.className = 'seg';
      d.style.cssText = `left:${pct(x)};width:${pct(v)};--c:${color(o)}`;
      x += v;
      return d;
    }));
    const label = rows[i].querySelector('.total');
    label.style.left = pct(x);
    label.textContent = x > EPS ? fmt(x) : '';   // no 0 next to eliminated candidates
    const support = rows[i].querySelector('.support');   // a winner's first choices, largest first
    support.style.width = pct(x);
    support.replaceChildren(...(st == 'elected' ? [...by].filter(([, v]) => v > EPS).sort((a, b) => b[1] - a[1]) : []).map(([o, v]) => {
      const d = document.createElement('div');
      d.style.cssText = `flex:${v};--c:${color(o)}`;
      return d;
    }));
    if (i == tipAt) renderTip();   // keep an open popup current as votes move
  };
  const draw = s => {
    names.forEach((_, i) => paint(i, s.status[i]));
    paint(T, 'trash');
  };
  // Move one step's votes: cut them off the source bar, then add each recipient's share to the end of
  // their bar and the lost votes to the non-transferable row, flying chips across when animating. Each
  // chip is a little stack of the voters' first choices it carries.
  const transfer = async (s, animate) => {
    const src = s.from, keep = s.votes[src], before = stages[stage - 1];   // keep: quota after a surplus, 0 after an elimination
    const moves = [...Object.entries(s.transfers).map(([to, amt]) => [+to, amt]), ...(s.lost > EPS ? [[T, s.lost]] : [])];
    paint(src, s.status[src]);
    if (animate) {
      const gained = to => {   // what a row gains, by first choice, in the source bar's order
        const now = comp(to), was = to == T ? before.lostSoFar : before.byFirst[to];
        return [...new Set([...order[src], ...now.keys()])].map(o => [o, (now.get(o) ?? 0) - (was.get(o) ?? 0)]).filter(([, v]) => v > EPS);
      };
      let x = keep;
      const chips = moves.map(([to, amt]) => {
        const chip = document.createElement('div');
        chip.className = to == T ? 'chip lost' : 'chip';
        chip.style.cssText = `left:${pct(x)};width:${pct(amt)};top:${rows[src].offsetTop}px;--fly:${1 / speed()}s`;
        chip.append(...gained(to).map(([o, v]) => {
          const d = document.createElement('div');
          d.style.cssText = `flex:${v};--c:${color(o)}`;
          return d;
        }));
        x += amt;
        $('chart').append(chip);
        return chip;
      });
      $('chart').offsetWidth;   // force layout so the moves below animate
      chips.forEach((chip, k) => {
        const to = moves[k][0];
        chip.style.left = pct(to == T ? total(before.lostSoFar) : before.votes[to]);   // to the end of the receiving bar
        chip.style.top = rows[to].offsetTop + 'px';
      });
      await sleep(1000);
      chips.forEach(chip => chip.remove());
    }
    for (const [to] of moves) paint(to, to == T ? 'trash' : s.status[to]);
  };
  const mark = i => { stage = shown = i; steps.forEach((li, j) => li.className = j < i ? 'done' : j == i ? 'now' : ''); };

  mark(0);
  draw(stages[0]);
  for (let i = 1; i <= start; i++) {   // jump: replay the earlier steps instantly
    mark(i);
    if (stages[i].from != null) await transfer(stages[i], false);
    draw(stages[i]);
  }
  for (let i = start + 1; i < stages.length; i++) {
    await hold(1500);
    if (me != run) return;
    mark(i);
    if (stages[i].from != null) await transfer(stages[i], true);
    if (me != run) return;
    draw(stages[i]);
  }
  await sleep(1500);   // hold the final state, so a video ends on it
}

async function open(e) {
  const text = await get(ROOT + e.election);
  if (location.hash.slice(1) != e.id) return;   // another election was picked meanwhile
  const { parties, ballots } = parseElection(text);
  current = { e, names: e.names.split('|'), parties, ballots };   // full names from the index
  const playing = show(current);
  if (matchMedia('(max-width: 760px)').matches) $('view').scrollIntoView({ behavior: 'smooth' });   // phones: down from the list to the chart
  await playing;
}

function route() {
  const e = elections.get(location.hash.slice(1));
  document.querySelector('nav [aria-current]')?.removeAttribute('aria-current');
  $('intro').hidden = !!e;
  if (!e) { run++; $('view').hidden = true; return; }   // no ward picked: stop any count, show the intro
  e.link.setAttribute('aria-current', 'page');
  for (let d = e.link.closest('details'); d; d = d.parentElement.closest('details')) d.open = true;
  e.link.scrollIntoView({ block: 'nearest' });
  open(e).catch(err => { $('view').hidden = false; $('heading').textContent = `Could not load ${e.id}: ${err.message}`; });
}
addEventListener('hashchange', route);

get('elections.csv').then(text => {
  const [head, ...body] = lines(text).map(cells);
  const group = (parent, label) => { const d = tpl('group'); d.firstElementChild.textContent = label; parent.append(d); return d; };
  $('index').replaceChildren();
  const all = body.map(r => Object.fromEntries(head.map((h, i) => [h, r[i]])));
  for (const [year, inYear] of Map.groupBy(all, e => e.year)) {
    const y = group($('index'), `${year} (${inYear.length})`);
    for (const [council, list] of Map.groupBy(inYear, e => e.council)) {
      const ul = group(y, `${council} (${list.length})`).appendChild(document.createElement('ul'));
      for (const e of list) {
        const li = tpl('ward');
        e.seats = +e.seats;
        e.link = li.querySelector('a');
        e.link.href = '#' + e.id;
        e.link.textContent = e.ward;
        li.querySelector('small').textContent = `${e.seats} seats, ${e.candidates} candidates`;
        ul.append(li);
        elections.set(e.id, e);
      }
    }
  }
  route();
}).catch(err => {
  $('index').textContent = `Could not load the election list (${err.message}). This page needs a local web server: in the repo root run "python3 -m http.server 8000", then open http://localhost:8000/viz/ (other options in viz/README.md).`;
});

// Record the current count without screen capture: replay it while copying the stage onto a canvas
// every frame, and encode the canvas. The video keeps one size, so the encoder never restarts.
// MP4 where MediaRecorder supports it (Safari, recent Chrome and Edge), else WebM (Firefox).
const VIDEO = window.MediaRecorder && HTMLCanvasElement.prototype.captureStream
  ? ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm'].find(t => MediaRecorder.isTypeSupported(t)) : null;
const recLabel = VIDEO?.includes('mp4') ? 'Download MP4' : 'Download WebM';
const lock = on => {   // while recording: no controls, clicks or scrolling
  hideTip();
  for (const id of ['rec', 'replay', 'prev', 'pause', 'next']) $(id).disabled = on;
  $('rec').textContent = on ? 'Recording…' : recLabel;
  document.body.classList.toggle('recording', on);
};
async function record() {
  const stage = $('stage');
  $('rec-msg').textContent = '';
  setPaused(false);
  lock(true);
  try {
    const playing = show(current);   // builds the stage right away, then animates
    const steps = [...$('steps').children], was = steps.map(li => li.className);
    steps.forEach(li => li.className = 'now');   // measure the tallest layout: every step bold
    const box = stage.getBoundingClientRect();
    steps.forEach((li, i) => li.className = was[i]);
    const k = Math.min(devicePixelRatio || 1, 2), even = n => Math.ceil(n * k / 2) * 2;   // H.264 wants even sizes
    const canvas = Object.assign(document.createElement('canvas'), { width: even(box.width), height: even(box.height) });
    const g = canvas.getContext('2d');
    const rec = new MediaRecorder(canvas.captureStream(30), { mimeType: VIDEO, videoBitsPerSecond: 8e6 });   // bitrate: raise if text looks soft
    const parts = [];
    rec.ondataavailable = e => parts.push(e.data);
    const stopped = new Promise(r => rec.onstop = r);
    let on = true;
    const tick = () => { if (on) { drawStage(g, k, stage); requestAnimationFrame(tick); } };
    tick();
    rec.start();
    await playing;
    on = false;
    rec.stop();
    await stopped;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(parts, { type: rec.mimeType }));
    a.download = current.e.id + (rec.mimeType.includes('mp4') ? '.mp4' : '.webm');
    a.click();
  } catch (err) {
    $('rec-msg').textContent = `Recording failed: ${err.message}`;
  } finally {
    lock(false);
  }
}
$('rec').textContent = recLabel;
$('rec').hidden = !VIDEO;
$('rec').onclick = record;
$('replay').onclick = () => { setPaused(false); show(current); };   // replay always plays, even after a pause
$('pause').onclick = () => { setPaused(!paused); paused ? waiting?.stop() : waiting?.go(); };
$('next').onclick = () => { setPaused(true); waiting?.go(); };
$('prev').onclick = () => { setPaused(true); show(current, Math.max(0, shown - 1)); };
$('sort').onchange = () => reorder();

// the popup: follows the mouse over a row, or opens where a row is tapped; a tap elsewhere closes it
function renderTip() {
  const d = tipInfo(tipAt), tip = $('tip');
  if (!d) return hideTip();
  const [head, party, votes] = tip.querySelector('.head').children;
  head.textContent = d.head;
  party.textContent = d.party;
  votes.textContent = d.votes ?? '';
  tip.querySelector('.sub').textContent = d.sub;
  tip.querySelector('tbody').replaceChildren(...d.rows.map(r => {
    const tr = tpl('tip-row'), [dot, who, n, pc] = tr.children;
    dot.firstChild.style.setProperty('--c', r.color);
    who.firstChild.textContent = r.who;
    who.lastChild.textContent = r.party;
    n.textContent = r.votes;
    pc.textContent = r.share;
    return tr;
  }));
  tip.hidden = false;
}
function hideTip() { tipAt = -1; $('tip').hidden = true; }
function showTip(e) {
  const row = e.target.closest('.row');
  if (!row) return hideTip();
  tipAt = +row.dataset.i;
  renderTip();
  const tip = $('tip'), w = tip.offsetWidth, h = tip.offsetHeight;   // keep it inside the window
  tip.style.left = (e.clientX + 14 + w > innerWidth ? Math.max(4, e.clientX - w - 14) : e.clientX + 14) + 'px';
  tip.style.top = (e.clientY + 14 + h > innerHeight ? Math.max(4, e.clientY - h - 14) : e.clientY + 14) + 'px';
}
$('rows').addEventListener('pointermove', e => e.pointerType == 'mouse' && showTip(e));
$('rows').addEventListener('pointerleave', e => e.pointerType == 'mouse' && hideTip());
$('rows').addEventListener('click', showTip);   // taps on touch screens
document.addEventListener('pointerdown', e => { if (!e.target.closest('#rows')) hideTip(); });

// Paint the stage onto a canvas from the page's live layout: every box with a background or a left
// border (bars, chunks, hatching, dividers, strips, dots, the dashed quota line), then text word by word where
// the browser placed it. Covers what this page draws, nothing more.
function drawStage(g, k, stage) {
  const o = stage.getBoundingClientRect();
  // boxes snap to whole canvas pixels, so touching chunks show no light seams between them
  const X = v => Math.round((v - o.left) * k), Y = v => Math.round((v - o.top) * k);
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.fillStyle = '#fff';
  g.fillRect(0, 0, g.canvas.width, g.canvas.height);
  for (const el of stage.querySelectorAll('*')) {   // document order: children paint over parents
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);   // chips report their mid-flight position
    if (!r.width || !r.height) continue;   // also skips display: none
    const x = X(r.left), y = Y(r.top), w = X(r.right) - x, h = Y(r.bottom) - y;
    if (cs.backgroundColor != 'rgba(0, 0, 0, 0)') {
      g.fillStyle = cs.backgroundColor;
      if (cs.borderRadius == '50%') { g.beginPath(); g.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, 2 * Math.PI); g.fill(); }
      else g.fillRect(x, y, w, h);
    }
    if (cs.backgroundImage != 'none') {   // the hatched non-transferable chunks: stripes in their --c colour
      g.save();
      g.beginPath(); g.rect(x, y, w, h); g.clip();
      g.fillStyle = '#fff'; g.fillRect(x, y, w, h);
      g.strokeStyle = cs.getPropertyValue('--c').trim();
      g.lineWidth = 3 * k;
      for (let d = -h; d < w; d += 7 * Math.SQRT2 * k) { g.beginPath(); g.moveTo(x + d, y); g.lineTo(x + d + h, y + h); g.stroke(); }
      g.restore();
    }
    const bw = Math.round(parseFloat(cs.borderLeftWidth) * k);   // 0 when there is none
    g.fillStyle = cs.borderLeftColor;
    if (bw && cs.borderLeftStyle == 'dashed') for (let d = y; d < y + h; d += 10 * k) g.fillRect(x, d, bw, Math.min(6 * k, y + h - d));
    else if (bw) g.fillRect(x, y, bw, h);
  }
  g.setTransform(k, 0, 0, k, -o.left * k, -o.top * k);   // text in page coordinates
  g.lineWidth = 1;
  const range = document.createRange(), walk = document.createTreeWalker(stage, NodeFilter.SHOW_TEXT);
  for (let t; (t = walk.nextNode());) {
    const cs = getComputedStyle(t.parentElement);
    g.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    g.fillStyle = g.strokeStyle = cs.color;
    const descent = g.measureText(t.data).fontBoundingBoxDescent;
    for (const m of t.data.matchAll(/\S+/g)) {
      range.setStart(t, m.index);
      range.setEnd(t, m.index + m[0].length);
      const r = range.getBoundingClientRect();
      g.fillText(m[0], r.left, r.bottom - descent);
    }
    if (t.parentElement.closest('.out .name')) {   // eliminated candidates are struck through
      range.selectNodeContents(t);
      const r = range.getBoundingClientRect(), y = r.top + r.height * 0.55;
      g.beginPath(); g.moveTo(r.left, y); g.lineTo(r.right, y); g.stroke();
    }
  }
}
