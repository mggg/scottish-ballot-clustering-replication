// Check the page's STV count against the published vote tables. Run from the repo root:
//     node viz/check.mjs
// Every election in viz/elections.csv is counted from its ballots by the same code the page runs, and
// each round's totals are compared with its vote table; it also checks that no vote goes missing.
// Exits with status 1 if anything differs.
import { readFileSync } from 'node:fs';

const page = readFileSync('viz/index.html', 'utf8');
const script = page.slice(page.indexOf('<script>') + '<script>'.length, page.indexOf('// Everything above runs without a browser'));
const problems = [];   // the page's own self-checks report here too
const { count, parseElection, cells, lines } = new Function('console', `${script}; return { count, parseElection, cells, lines };`)(
  { assert: (ok, message) => ok || problems.push(message) });

const [head, ...rows] = lines(readFileSync('viz/elections.csv', 'utf8')).map(cells);
let worst = 0;
for (const row of rows) {
  const e = Object.fromEntries(head.map((h, i) => [h, row[i]]));
  const { seats, ballots } = parseElection(readFileSync(e.election, 'utf8'));
  const table = lines(readFileSync(e.table, 'utf8')).slice(1).map(cells);   // Candidate, Round 1, Round 2, ...
  const rounds = table[0].slice(1).map((_, r) => table.map(t => +t[r + 1]));
  const { stages } = count(e.names.split('|'), seats, ballots);
  // every vote is somewhere: with a candidate, or in the lost votes (whose first choices add up too)
  const cast = ballots.reduce((t, b) => t + b.n, 0), sum = m => [...m.values()].reduce((a, b) => a + b, 0);
  if (stages.some(s => Math.abs(s.votes.reduce((a, b) => a + b, 0) + sum(s.trash) - cast) > 1e-6)) problems.push(`${e.id}: votes don't add up to the ballots cast`);
  // the page's stages are the table's rounds, plus closing steps that move no votes
  const ours = stages.filter((s, i) => i == 0 || s.from != null).map(s => s.votes);
  if (ours.length != rounds.length) { problems.push(`${e.id}: ${ours.length} rounds, but the table has ${rounds.length}`); continue; }
  const gap = Math.max(...ours.flatMap((votes, r) => votes.map((v, c) => Math.abs(v - rounds[r][c]))));
  worst = Math.max(worst, gap);
  if (gap > 1e-6) problems.push(`${e.id}: off by up to ${gap.toFixed(5)} votes`);
}
console.log(problems.length ? problems.join('\n') : `All ${rows.length} counts match their vote tables (largest gap ${worst.toExponential(1)} votes).`);
process.exitCode = problems.length ? 1 : 0;
