// The STV count, rebuilt from the published vote tables, and reading the data files it needs. Nothing
// here touches the page, so both the page (app.mjs) and the checks (check.mjs) import it.

export const EPS = 1e-6;   // vote differences smaller than this are floating-point noise
export const fmt = n => +n.toFixed(2);   // votes for display: at most two decimal places
export const lines = text => text.trim().split(/\r?\n/);
// one CSV line -> fields, honoring "quoted, fields" and "" escapes
export const cells = line => [...line.matchAll(/(?:^|,)("(?:[^"]|"")*"|[^,]*)/g)].map(m => m[1].replace(/^"(.*)"$/s, '$1').replaceAll('""', '"'));

// Rebuild an election's count from its vote table, where votes[round][candidate] is each candidate's
// total after each round:
// - The quota is the votes divided by one more than the seats, rounded down, plus one. Reaching it elects.
// - Every table moves one candidate's votes per round: a winner's surplus, which cuts them back to the
//   quota, or all the votes of the candidate eliminated, which cuts them to zero.
// - The rises in other totals are the transfers. Whatever they don't cover is non-transferable.
// The tables only record totals, so they can't say who the moved votes' voters first chose. Instead,
// each stage records every candidate's votes by who last passed them on (a candidate's own first
// preferences count as their own), and the lost votes by whose transfer lost them. When a winner's
// surplus moves, the winner keeps the same share of every part.
//
// Returns the quota and the stages, each { votes, bySender, lostSoFar, status, note }, plus
// { from, transfers, lost } on stages that move votes.
export function count(names, votes, seats) {
  const cast = votes[0].reduce((a, b) => a + b, 0);
  const quota = Math.floor(cast / (seats + 1)) + 1;
  const status = names.map(() => 'hopeful');   // becomes 'elected' or 'out'
  const withStatus = st => status.flatMap((x, c) => x == st ? [c] : []);
  const nameList = cs => cs.map(c => names[c]).join(' and ');

  // Each candidate's votes by who last passed them on, and the lost votes by whose transfer lost them.
  let bySender = names.map((_, c) => new Map([[c, votes[0][c]]]));
  let lostSoFar = new Map();

  const stages = [];
  // Elect anyone who has reached the quota, and record the stage.
  const recordStage = (round, note, move = {}) => {
    const newlyElected = withStatus('hopeful').filter(c => round[c] >= quota - EPS);
    for (const c of newlyElected) status[c] = 'elected';
    if (newlyElected.length) note += ` ${nameList(newlyElected)} elected.`;
    stages.push({ votes: round, bySender, lostSoFar, status: [...status], note, ...move });
  };

  recordStage(votes[0], `First preferences: ${fmt(cast)} votes for ${seats} seats, quota ${quota}.`);
  for (let r = 1; r < votes.length; r++) {
    const before = votes[r - 1], after = votes[r];

    // The one candidate whose total fell is the one whose votes moved.
    const from = after.findIndex((v, c) => v - before[c] < -EPS);
    if (from < 0) throw Error(`round ${r + 1}: no candidate lost votes`);
    const isSurplus = status[from] == 'elected';
    if (!isSurplus) status[from] = 'out';
    const moved = before[from] - after[from];

    // What each candidate gained. The rest is lost: ballots with no choices left, and rounding.
    const transfers = {};
    after.forEach((v, c) => { if (v - before[c] > EPS) transfers[c] = v - before[c]; });
    const lost = moved - Object.values(transfers).reduce((a, b) => a + b, 0);

    // The source keeps the same share of every part (none, if eliminated). Each recipient, and the
    // lost votes, gain a part from the source.
    const kept = after[from] / before[from];
    bySender = bySender.map((parts, c) => {
      if (c == from) return new Map([...parts].map(([s, v]) => [s, v * kept]).filter(([, v]) => v > EPS));
      return transfers[c] ? new Map([...parts, [from, (parts.get(from) ?? 0) + transfers[c]]]) : parts;
    });
    if (lost > EPS) lostSoFar = new Map([...lostSoFar, [from, (lostSoFar.get(from) ?? 0) + lost]]);

    const note = isSurplus ? `${names[from]}'s surplus of ${fmt(moved)} transferred.`
      : `${names[from]} eliminated, ${fmt(moved)} votes transferred.`;
    recordStage(after, note + (lost > 0.005 ? ` ${fmt(lost)} non-transferable.` : ''), { from, transfers, lost });
  }

  // The closing stages move no votes, so they repeat the last tallies.
  const last = stages.at(-1);
  const closingStage = note => stages.push({ votes: last.votes, bySender: last.bySender, lostSoFar: last.lostSoFar, status: [...status], note });
  // Exactly as many candidates left as open seats: they fill them without reaching the quota.
  const left = seats - withStatus('elected').length;
  if (left > 0) {
    const fill = withStatus('hopeful').sort((a, b) => last.votes[b] - last.votes[a]).slice(0, left);
    for (const c of fill) status[c] = 'elected';
    closingStage(`${nameList(fill)} elected without reaching quota.`);
  }
  const winners = withStatus('elected').map(c => names[c]).join(', ');
  if (stages.length > 1) stages.at(-1).note += ` Elected: ${winners}.`;
  // Everyone else loses; their last votes never transfer.
  for (const c of withStatus('hopeful')) status[c] = 'out';
  closingStage('Election completed.');
  return { quota, stages };
}

// Read a vote table from data/scottish_vote_tables: a header (Candidate, Round 1, Round 2, ...), then one
// row per candidate with their total after each round. Its names are the full ones.
export function parseTable(text) {
  const rows = lines(text).slice(1).map(cells);
  return { names: rows.map(r => r[0]), votes: rows[0].slice(1).map((_, r) => rows.map(row => +row[r + 1])) };
}

// Read an election file from data/scot-elex: a first row of candidates and seats, then ballot rows
// (how many ballots, then candidate numbers from 1 in preference order), then one row per candidate
// with name and party, then the ward name. Candidates are in the same order as in the vote table.
export function parseElection(text) {
  const rows = lines(text);
  const candidates = rows.filter(l => l.startsWith('"Candidate ')).map(cells);
  return {
    seats: +rows[0].split(',')[1],
    parties: candidates.map(r => r[2].match(/\(([^()]*)\)\s*$/)?.[1] ?? ''),
    ballots: rows.slice(1).filter(l => /^\d/.test(l)).map(l => {
      const f = l.split(',').filter(Boolean).map(Number);
      return { n: f[0], prefs: f.slice(1).map(c => c - 1) };
    }),
  };
}
