// Check the STV count: node viz/check.mjs
// First a few hand-worked vote tables, then every election in viz/elections.csv: its count rebuilds
// and fills every seat, its vote table's first round matches its ballots, and no vote goes missing at
// any stage. Exits with status 1 if anything is wrong.
import { readFileSync } from 'node:fs';
import { count, parseTable, parseElection, cells, lines } from './count.mjs';

const read = path => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');   // paths from the repo root
const problems = [];
const check = (ok, what) => ok || problems.push(`check failed: ${what}`);
const total = parts => [...parts.values()].reduce((a, b) => a + b, 0);

// 2 seats, quota 4. D is eliminated and D's 2 votes go to A, who passes the quota. A's surplus of 1
// goes to B. Then B, with more votes than C, fills the last seat.
{
  const { quota, stages } = count(['A', 'B', 'C', 'D'], [[3, 2, 2, 2], [5, 2, 2, 0], [4, 3, 2, 0]], 2);
  check(quota == 4 && stages[1].from == 3 && stages[1].transfers[0] == 2, 'reading a transfer from the totals');
  check(stages[2].from == 0 && stages[2].transfers[1] == 1, 'reading a surplus from the totals');
  const a = stages[2].bySender[0];   // A had 3 own votes and 2 from D, and keeps 4 of 5: the same share of each
  check(Math.abs(a.get(0) - 2.4) < 1e-9 && Math.abs(a.get(3) - 1.6) < 1e-9, 'a winner keeps the same share of every part');
  const b = stages[2].bySender[1];   // B: 2 own votes, and 1 passed on by A
  check(b.get(1) == 2 && b.get(0) == 1, 'votes by who last passed them on');
  check(stages.at(-2).note.startsWith('B elected without reaching quota') && stages.at(-1).status.join() == 'elected,elected,out,out', 'filling the last seat');
  check(stages.at(-1).note == 'Election completed.', 'the final stage');
}
// 2 seats, quota 3. A reaches it exactly; C's lone vote is lost when C is eliminated.
{
  const { stages } = count(['A', 'B', 'C'], [[3, 2, 1], [3, 2, 0]], 2);
  check(stages[1].lost == 1 && stages[1].lostSoFar.get(2) == 1, "a vote that can't transfer is lost");
}
check(cells('a,"b, ""c""",').join('|') == 'a|b, "c"|', 'reading quoted CSV fields');

// Every election.
const [head, ...rows] = lines(read('viz/elections.csv')).map(cells);
for (const row of rows) {
  const e = Object.fromEntries(head.map((h, i) => [h, row[i]]));
  const { names, votes } = parseTable(read(e.table));
  const { seats, parties, ballots } = parseElection(read(e.election));
  let stages;
  try { ({ stages } = count(names, votes, seats)); } catch (err) { problems.push(`${e.id}: ${err.message}`); continue; }
  if (parties.length != names.length) problems.push(`${e.id}: ${parties.length} parties for ${names.length} candidates`);
  if (stages.at(-1).status.filter(s => s == 'elected').length != seats) problems.push(`${e.id}: doesn't fill ${seats} seats`);
  // the vote table's first round is the ballots' first preferences
  const firsts = names.map(() => 0);
  for (const b of ballots) firsts[b.prefs[0]] += b.n;
  if (firsts.some((v, c) => Math.abs(v - votes[0][c]) > 1e-6)) problems.push(`${e.id}: the first round doesn't match the ballots`);
  // every vote is somewhere: with a candidate, whose parts add up to their total, or lost
  const cast = firsts.reduce((a, b) => a + b, 0);
  if (stages.some(s => s.bySender.some((parts, c) => Math.abs(total(parts) - s.votes[c]) > 1e-6)
    || Math.abs(s.votes.reduce((a, b) => a + b, 0) + total(s.lostSoFar) - cast) > 1e-6)) problems.push(`${e.id}: votes go missing`);
}
console.log(problems.length ? problems.join('\n') : `All checks pass, for all ${rows.length} elections.`);
process.exitCode = problems.length ? 1 : 0;
