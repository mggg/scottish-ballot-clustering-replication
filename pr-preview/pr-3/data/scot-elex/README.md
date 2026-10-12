# Scottish Election Information

This directory contains cast vote records from Scottish local government elections held in 2007,
2012, 2017, and 2022. [David McCune](https://www.jewell.edu/faculty/david-mccune) originally
assembled and cleaned the records from Scottish sources, producing 1,100 files in BLT format. The
CSV collection here contains the 1,070 elections with party labels; it excludes 30 by-elections that
lack those labels.

These elections use Single Transferable Vote (STV). Voters rank candidates, who are elected when
their vote totals reach a threshold related to the number of seats. Surplus votes transfer to
remaining candidates according to voters' rankings. When no candidate reaches the threshold, a
candidate is eliminated and their votes transfer; counting continues until enough candidates are
elected.

## How to read the CSV files

The CSV files follow a structure similar to the source BLT files. Read them in four sections:

- **First row:** Number of candidates and number of seats.
- **Ballot rows:** A frequency followed by candidate IDs in preference order. For example,
  `12,3,1,2` represents 12 ballots ranking candidate 3 above 1 above 2.
- **Candidate rows:** Candidate names and party labels, listed in candidate ID order.
- **Last row:** The ward where the election was held. The election year appears in the filename.

### Example

This example has three candidates competing for two seats:

```
3,2,
12,1,
88,1,3,2,
14,2,3,
8,3,
"Candidate 1","Alvin the First","Party A (A)",
"Candidate 2","Becca the Second","Party B (B)",
"Candidate 3","Carrie the Third","Party C (C)",
"Wardy McWard Town",
```

The annotations below show how the ballot rows refer to the candidate list:

```
3,2,                                                # There are 3 candidates running for 2 seats
12,1,                                               # 12 Bullet votes for candidate 1 were cast
88,1,3,2,                                           # 88 Ballots ranking 1>3>2 were cast
14,2,3,
8,3,
"Candidate 1","Alvin the First","Party A (A)",      # The name of candidate 1 and their party
"Candidate 2","Becca the Second","Party B (B)",
"Candidate 3","Carrie the Third","Party C (C)",
"Wardy McWard Town",                                # The name of the ward
```

## List of Parties in 2007, 2012, 2017, and 2022 Elections

- Alba Party for Independence (API)
- Borders (Borders)
- Britannica Party (BP)
- British National Party (BNP)
- British Unionists (BU)
- Christian Peoples Alliance (CPA)
- Communist Party of Britain (Comm)
- (Scottish) Conservative and Unionist Party (Con)
- Cumbernauld Independent Councillors Alliance (CICA)
- East Dunbartonshire Independent Alliance (EDIA)
- East Kilbride Alliance (EKA)
- Freedom Alliance (FA)
- Glasgow First (Glasgow First)
- (Scottish) Green (Gr)
- Independence for Scotland Party (ISP)
- Independent (Ind)
- Independent Alliance North Lanarkshire (IANL)
- Labour (Lab)
- Labour and Co-operative Party (LabCo)
- Liberal (Lib)
- Liberal Democrat (LD)
- Libertarian (Libtn)
- Monster Raving Loony (MVR)
- National Front (NF)
- No Referendum, Maintain Union, Pro-Brexit (NRMUPB)
- Orkney Manifesto Group (OMG)
- Piarate (Pir)
- RISE (RISE)
- Rubbish (Rubbish)
- Scotland Independent Network (ScIN)
- Scottish Christian (SC)
- Scottish Eco-Federalist Party (SEFP)
- Scottish Family Party (SFP)
- Scottish National Party (SNP)
- Scottish Senior Citizens (SSC)
- Scottish Unionist (SU)
- Social Democratic Party (SDP)
- Socialist (Soc)
- Socialist Labour Party (SLP)
- Solidarity (Sol)
- Sovereignty (Sov)
- The Pensioner's Party (TPP)
- Trade Unionist and Socialist Coalition (TUSC)
- UK Independence Party (UKIP)
- Vanguard Party (Van)
- Volt UK (Volt)
- West Dunbartonshire Community (WDuns)
- Women's Equality Party (WEP)
- Worker Party of Britain (WPB)
