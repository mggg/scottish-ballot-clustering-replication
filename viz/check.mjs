// Check the STV count: node viz/check.mjs
// First a few hand-worked elections, then every election in viz/elections.csv, counted from its ballots
// and compared round by round with its published vote table, checking that no vote goes missing.
// Exits with status 1 if anything is wrong.
import { readFileSync } from 'node:fs';
import { count, parseElection, cells, lines } from './count.mjs';

const read = path => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');   // paths from the repo root
const problems = [];
const check = (ok, what) => ok || problems.push(`check failed: ${what}`);

// 2 seats, quota 4. A wins outright and A's surplus of 1 goes to B. C is eliminated, and C's ballots
// skip A (already elected) to reach B, who takes the second seat.
{
  const { quota, stages } = count(['A', 'B', 'C'], 2, [{ n: 5, prefs: [0, 1] }, { n: 2, prefs: [1] }, { n: 2, prefs: [2, 0, 1] }]);
  check(quota == 4 && stages[1].from == 0 && stages[1].transfers[1] == 1, 'a surplus moves to the next choice');
  check(stages[2].transfers[1] == 2 && !stages[2].transfers[0], 'ballots skip a candidate already elected');
  check(stages.at(-1).status.join() == 'elected,elected,out' && stages.at(-1).note == 'Election completed.', 'winners and the final stage');
  const b = stages[2].byFirst[1];   // B: 2 own first preferences, 1 that started with A, 2 that started with C
  check(Math.abs(b.get(0) - 1) < 1e-9 && b.get(1) == 2 && b.get(2) == 2, 'votes by first choice');
}
// 2 seats, quota 3. A reaches it exactly; C's lone ballot runs out when C is eliminated; B fills the last seat.
{
  const { stages } = count(['A', 'B', 'C'], 2, [{ n: 3, prefs: [0] }, { n: 2, prefs: [1] }, { n: 1, prefs: [2] }]);
  check(stages[1].lost == 1 && stages[1].lostSoFar.get(2) == 1, 'a ballot that runs out is lost');
  check(stages.at(-2).note.startsWith('B elected without reaching quota') && stages.at(-1).status.join() == 'elected,elected,out', 'filling the last seat');
}
check(cells('a,"b, ""c""",').join('|') == 'a|b, "c"|', 'reading quoted CSV fields');

// Every election, against its published vote table.
const [head, ...rows] = lines(read('viz/elections.csv')).map(cells);
let worst = 0;
for (const row of rows) {
  const e = Object.fromEntries(head.map((h, i) => [h, row[i]]));
  const { seats, ballots } = parseElection(read(e.election));
  const table = lines(read(e.table)).slice(1).map(cells);   // Candidate, Round 1, Round 2, ...
  const rounds = table[0].slice(1).map((_, r) => table.map(t => +t[r + 1]));
  const { stages } = count(e.names.split('|'), seats, ballots);
  // every vote is somewhere: with a candidate, or in the lost votes (whose first choices add up too)
  const cast = ballots.reduce((t, b) => t + b.n, 0), sum = m => [...m.values()].reduce((a, b) => a + b, 0);
  if (stages.some(s => Math.abs(s.votes.reduce((a, b) => a + b, 0) + sum(s.lostSoFar) - cast) > 1e-6)) problems.push(`${e.id}: votes don't add up to the ballots cast`);
  // the page's stages are the table's rounds, plus closing stages that move no votes
  const ours = stages.filter((s, i) => i == 0 || s.from != null).map(s => s.votes);
  if (ours.length != rounds.length) { problems.push(`${e.id}: ${ours.length} rounds, but the table has ${rounds.length}`); continue; }
  const gap = Math.max(...ours.flatMap((votes, r) => votes.map((v, c) => Math.abs(v - rounds[r][c]))));
  worst = Math.max(worst, gap);
  if (gap > 1e-6) problems.push(`${e.id}: off by up to ${gap.toFixed(5)} votes`);
}
console.log(problems.length ? problems.join('\n') : `All checks pass, and all ${rows.length} counts match their vote tables (largest gap ${worst.toExponential(1)} votes).`);
process.exitCode = problems.length ? 1 : 0;
