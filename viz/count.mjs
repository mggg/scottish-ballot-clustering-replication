// The STV count, and reading the data files it needs. Nothing here touches the page, so both the page
// (app.mjs) and the checks (check.mjs) import it.

export const EPS = 1e-6;   // vote differences smaller than this are floating-point noise
export const fmt = n => +n.toFixed(2);   // votes for display: at most two decimal places
export const lines = text => text.trim().split(/\r?\n/);
// one CSV line -> fields, honoring "quoted, fields" and "" escapes
export const cells = line => [...line.matchAll(/(?:^|,)("(?:[^"]|"")*"|[^,]*)/g)].map(m => m[1].replace(/^"(.*)"$/s, '$1').replaceAll('""', '"'));

// Count an election from its ballots under Scotland's STV rules, one stage at a time:
// - The quota is the votes divided by one more than the seats, rounded down, plus one. Reaching it elects.
// - Each stage moves one candidate's ballots on to their next choice still in the race: a winner's
//   surplus if one is waiting (earliest winner first, then the largest), or else every ballot of the
//   candidate in last place, who is eliminated.
// - A surplus moves every ballot the winner holds at a transfer value rounded down to five decimal
//   places, so together they carry the surplus; the winner keeps the quota.
// - Ties go by the earliest stage where the candidates' totals differed, then by ballot order.
// Every pile of identical ballots remembers its voters' first choice, so each stage also records every
// candidate's votes by first choice, and the votes lost so far by first choice.
// This reproduces all 1,070 vote tables in data/scottish_vote_tables exactly; `node viz/check.mjs`
// re-checks.
//
// ballots: [{ n, prefs }] — n identical ballots ranking the candidate indexes in prefs.
// Returns the quota and the stages, each { votes, byFirst, lostSoFar, status, note }, plus
// { from, transfers, lost } on stages that move votes.
export function count(names, seats, ballots) {
  const cast = ballots.reduce((sum, b) => sum + b.n, 0);
  const quota = Math.floor(cast / (seats + 1)) + 1;

  // A pile is a group of identical ballots: how far down its ranking it is, and what each ballot is worth.
  const piles = ballots.map(b => ({ n: b.n, prefs: b.prefs, rank: 0, value: 1 }));
  const holder = pile => pile.prefs[pile.rank];   // undefined once the ranking runs out

  const status = names.map(() => 'hopeful');   // becomes 'elected' or 'out'
  const electedAt = names.map(() => Infinity);   // the stage each winner reached the quota
  const retained = names.map(() => null);   // a winner's votes by first choice, once their surplus has moved
  const withStatus = st => status.flatMap((x, c) => x == st ? [c] : []);
  const openSeats = () => seats - withStatus('elected').length;

  const total = byFirst => [...byFirst.values()].reduce((a, b) => a + b, 0);
  const nameList = cs => cs.map(c => names[c]).join(' and ');
  // Compare two vote totals; differences below EPS are floating-point noise, so they count as ties.
  const compare = (x, y) => Math.abs(x - y) < EPS ? 0 : x - y;

  // A candidate's votes, split by the first choice of the voters behind them.
  const votesByFirst = c => {
    if (retained[c]) return retained[c];
    const byFirst = new Map();
    for (const pile of piles) {
      if (holder(pile) !== c) continue;
      const first = pile.prefs[0];
      byFirst.set(first, (byFirst.get(first) ?? 0) + pile.n * pile.value);
    }
    return byFirst;
  };

  const stages = [];
  // Tally the votes, elect anyone who has reached the quota, and record the stage.
  const recordStage = (note, move = {}) => {
    const byFirst = names.map((_, c) => votesByFirst(c));
    const votes = byFirst.map(total);
    // Votes lost so far, by first choice: each candidate's first preferences minus what still counts.
    const lostSoFar = new Map();
    if (stages.length) names.forEach((_, first) => {
      const stillCounted = byFirst.reduce((sum, m) => sum + (m.get(first) ?? 0), 0);
      const lost = stages[0].votes[first] - stillCounted;
      if (lost > EPS) lostSoFar.set(first, lost);
    });
    const newlyElected = withStatus('hopeful').filter(c => votes[c] >= quota - EPS);
    for (const c of newlyElected) { status[c] = 'elected'; electedAt[c] = stages.length; }
    if (newlyElected.length) note += ` ${nameList(newlyElected)} elected.`;
    stages.push({ votes, byFirst, lostSoFar, status: [...status], note, ...move });
  };

  // Break a tie between two candidates by the earliest stage where their totals differed.
  const earliestDifference = (a, b) => {
    for (const stage of stages) {
      const d = compare(stage.votes[a], stage.votes[b]);
      if (d) return d;
    }
    return 0;
  };

  recordStage(`First preferences: ${fmt(cast)} votes for ${seats} seats, quota ${quota}.`);
  // Keep going while seats are open and more candidates are left than open seats.
  while (openSeats() > 0 && withStatus('hopeful').length > openSeats()) {
    const votes = stages.at(-1).votes;

    // Whose ballots move: the first waiting surplus, or else the candidate in last place.
    const surpluses = withStatus('elected')
      .filter(c => !retained[c] && votes[c] > quota + EPS)
      .sort((a, b) => electedAt[a] - electedAt[b]   // earliest winner first
        || compare(votes[b], votes[a])              // then the largest
        || earliestDifference(b, a) || a - b);      // then ties
    const lastPlace = () => withStatus('hopeful')
      .sort((a, b) => compare(votes[a], votes[b]) || earliestDifference(a, b) || a - b)[0];
    const isSurplus = surpluses.length > 0;
    const from = isSurplus ? surpluses[0] : lastPlace();
    const moved = isSurplus ? votes[from] - quota : votes[from];

    if (isSurplus) {
      // The winner keeps the quota, made of the same fraction of every ballot they hold.
      retained[from] = new Map([...votesByFirst(from)].map(([first, v]) => [first, v * quota / votes[from]]));
    } else {
      status[from] = 'out';
    }
    for (const pile of piles.filter(p => holder(p) === from)) {
      // The transfer value: surplus × the ballot's value ÷ the winner's total, rounded down to five places.
      if (isSurplus) pile.value = Math.floor(moved * pile.value / votes[from] * 1e5 + EPS) / 1e5;
      // On to the next choice still in the race, skipping winners and eliminated candidates.
      do pile.rank++; while (pile.rank < pile.prefs.length && status[pile.prefs[pile.rank]] != 'hopeful');
    }

    // What each candidate gained. The rest is lost: ballots with no choices left, and rounding.
    const transfers = {};
    names.forEach((_, c) => {
      const gain = total(votesByFirst(c)) - votes[c];
      if (gain > EPS) transfers[c] = gain;
    });
    const lost = moved - Object.values(transfers).reduce((a, b) => a + b, 0);
    const note = isSurplus ? `${names[from]}'s surplus of ${fmt(moved)} transferred.`
      : `${names[from]} eliminated, ${fmt(moved)} votes transferred.`;
    recordStage(note + (lost > 0.005 ? ` ${fmt(lost)} non-transferable.` : ''), { from, transfers, lost });
  }

  // The closing stages move no votes, so they repeat the last tallies.
  const { votes, byFirst, lostSoFar } = stages.at(-1);
  const closingStage = note => stages.push({ votes, byFirst, lostSoFar, status: [...status], note });
  // Exactly as many candidates left as open seats: they fill them without reaching the quota.
  const left = openSeats();
  if (left > 0) {
    const fill = withStatus('hopeful').sort((a, b) => votes[b] - votes[a]).slice(0, left);
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

// Read an election file from data/scot-elex: a first row of candidates and seats, then ballot rows
// (how many ballots, then candidate numbers from 1 in preference order), then one row per candidate
// with name and party, then the ward name.
export function parseElection(text) {
  const rows = lines(text);
  const candidates = rows.filter(l => l.startsWith('"Candidate ')).map(cells);
  return {
    seats: +rows[0].split(',')[1],
    names: candidates.map(r => r[1]),   // some are cut short at hyphens and accents; the index has full names
    parties: candidates.map(r => r[2].match(/\(([^()]*)\)\s*$/)?.[1] ?? ''),
    ballots: rows.slice(1).filter(l => /^\d/.test(l)).map(l => {
      const f = l.split(',').filter(Boolean).map(Number);
      return { n: f[0], prefs: f.slice(1).map(c => c - 1) };
    }),
  };
}
