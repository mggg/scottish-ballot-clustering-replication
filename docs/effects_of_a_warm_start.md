# Effects of a warm start

I selected 10 six-candidate elections at random from the Scottish dataset and tried to see if
giving the models a "warm start" would improve the solve time. By-and-large, providing a warm
start did not substantially improve the solve time or memory requirements in most cases, and I
think that it comes down to Gurobi having a lot of trouble proving the lower bound.

**Reading the tables:** C/W means cold/warm, each out of ten elections. H2H means head-to-head.
Election names throughout this report are the input filenames without the `.csv` extension.
Time C/W gives median full-process seconds over pairs where **both** reached OPTIMAL. Faster
counts those pairs where the warm run took less time. Percentage changes are medians of the
individual warm/cold changes, **not** changes between the displayed medians; negative favors warm.
RSS is peak process memory, including preparation. Each warm start is compared
with its own experiment's cold run.

## Coordinate target

| Metric | Start | Solved C/W | Faster |  Time C/W (s) | Time delta | RSS delta |
| ------ | ----- | ---------: | -----: | ------------: | ---------: | --------: |
| Borda  | Cast  |      10/10 |   4/10 |   82.44/50.91 |      +6.9% |    +23.6% |
| Borda  | PAM   |      10/10 |   4/10 |   81.12/51.93 |     +20.1% |     +1.6% |
| H2H    | Cast  |        7/7 |    3/7 | 244.40/148.94 |      +6.9% |     +4.3% |
| H2H    | PAM   |        7/7 |    4/7 | 226.42/145.19 |      -3.8% |     -1.5% |

### Borda by election

| Election                       | Start | Status C/W |  Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | ------------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | Cast  | O/O        |   10.45/14.30 |   114.9/171.6 |     +36.8% |
| aberdeenshire_2022_ward16      | PAM   | O/O        |   10.41/14.04 |   114.8/115.6 |     +34.8% |
| argyll_bute_2017_ward6         | Cast  | O/O        |   54.97/27.03 |   118.7/145.8 |     -50.8% |
| argyll_bute_2017_ward6         | PAM   | O/O        |   54.99/26.97 |   118.5/117.9 |     -51.0% |
| clackmannanshire_2017_ward5    | Cast  | O/O        |   17.30/13.93 |   112.0/139.3 |     -19.5% |
| clackmannanshire_2017_ward5    | PAM   | O/O        |   17.42/13.65 |   109.3/112.2 |     -21.6% |
| dumgal_2012_ward8              | Cast  | O/O        |   94.25/10.97 |   221.9/180.3 |     -88.4% |
| dumgal_2012_ward8              | PAM   | O/O        |   91.88/41.33 |   221.4/131.6 |     -55.0% |
| east_dunbartonshire_2022_ward5 | Cast  | O/O        |  98.47/172.10 |   144.1/245.8 |     +74.8% |
| east_dunbartonshire_2022_ward5 | PAM   | O/O        |  93.59/214.95 |   147.5/188.3 |    +129.7% |
| eilean_siar_2017_ward9         | Cast  | O/O        | 487.22/715.30 |   269.7/313.1 |     +46.8% |
| eilean_siar_2017_ward9         | PAM   | O/O        | 481.63/715.82 |   272.9/310.8 |     +48.6% |
| falkirk_2022_ward1             | Cast  | O/O        |   70.64/74.80 |   124.9/208.3 |      +5.9% |
| falkirk_2022_ward1             | PAM   | O/O        |   70.35/62.54 |   126.5/123.1 |     -11.1% |
| highland_2022_thurso           | Cast  | O/O        | 383.68/547.64 |   211.9/325.2 |     +42.7% |
| highland_2022_thurso           | PAM   | O/O        | 380.61/545.47 |   212.1/259.7 |     +43.3% |
| inverclyde_2017_ward3          | Cast  | O/O        |     3.98/4.30 |   102.1/114.2 |      +8.0% |
| inverclyde_2017_ward3          | PAM   | O/O        |     3.89/4.33 |   101.4/101.8 |     +11.1% |
| sc_borders_2012_ward4          | Cast  | O/O        | 455.10/431.96 |   220.6/266.3 |      -5.1% |
| sc_borders_2012_ward4          | PAM   | O/O        | 452.36/583.77 |   222.4/249.1 |     +29.1% |

### Head-to-head by election

| Election                       | Start | Status C/W |    Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | --------------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | Cast  | O/O        |   161.82/134.82 |   139.9/170.2 |     -16.7% |
| aberdeenshire_2022_ward16      | PAM   | O/O        |   177.68/145.19 |   138.0/136.8 |     -18.3% |
| argyll_bute_2017_ward6         | Cast  | O/O        |   625.60/973.99 |   216.7/284.1 |     +55.7% |
| argyll_bute_2017_ward6         | PAM   | O/O        |   623.44/966.47 |   215.1/280.6 |     +55.0% |
| clackmannanshire_2017_ward5    | Cast  | O/O        |   135.48/148.94 |   129.5/139.5 |      +9.9% |
| clackmannanshire_2017_ward5    | PAM   | O/O        |   134.99/142.65 |   132.8/135.0 |      +5.7% |
| dumgal_2012_ward8              | Cast  | O/O        |    244.40/85.66 |   153.1/181.8 |     -65.0% |
| dumgal_2012_ward8              | PAM   | O/O        |    226.42/87.98 |   154.8/127.6 |     -61.1% |
| east_dunbartonshire_2022_ward5 | Cast  | O/O        |   530.88/392.80 |   182.0/188.7 |     -26.0% |
| east_dunbartonshire_2022_ward5 | PAM   | O/O        |   491.31/380.76 |   184.9/185.8 |     -22.5% |
| eilean_siar_2017_ward9         | Cast  | T/T        | 3603.19/3603.48 | 3496.7/3257.9 |        n/a |
| eilean_siar_2017_ward9         | PAM   | T/T        | 3592.99/3592.51 | 3549.3/3108.6 |        n/a |
| falkirk_2022_ward1             | Cast  | O/O        | 1458.30/1558.37 |   309.7/315.1 |      +6.9% |
| falkirk_2022_ward1             | PAM   | O/O        | 1464.39/1408.34 |   313.2/296.5 |      -3.8% |
| highland_2022_thurso           | Cast  | T/T        | 3601.43/3602.37 | 1769.2/1544.3 |        n/a |
| highland_2022_thurso           | PAM   | T/T        | 3591.27/3591.00 | 1772.9/1518.2 |        n/a |
| inverclyde_2017_ward3          | Cast  | O/O        |     13.93/32.49 |   117.9/123.7 |    +133.2% |
| inverclyde_2017_ward3          | PAM   | O/O        |     13.94/22.66 |   114.1/111.8 |     +62.5% |
| sc_borders_2012_ward4          | Cast  | T/T        | 3601.76/3602.55 | 2341.1/2354.2 |        n/a |
| sc_borders_2012_ward4          | PAM   | T/T        | 3591.58/3591.63 | 2372.0/2372.2 |        n/a |

## All-ballot target

| Metric | Start | Solved C/W | Faster | Time C/W (s) | Time dellta | RSS delta |
| ------ | ----- | ---------: | -----: | -----------: | ----------: | --------: |
| Borda  | Cast  |      10/10 |   4/10 |  17.60/19.29 |       +5.8% |    +59.8% |
| Borda  | PAM   |      10/10 |   5/10 |  17.56/17.87 |       -0.8% |     +0.8% |
| H2H    | Cast  |      10/10 |   6/10 |    9.88/9.36 |       -6.9% |    +62.4% |
| H2H    | PAM   |      10/10 |   7/10 |    9.91/9.04 |       -5.0% |     -1.1% |

### Borda by election

| Election                       | Start | Status C/W |  Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | ------------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | Cast  | O/O        |   10.22/11.14 |   109.1/171.4 |      +8.9% |
| aberdeenshire_2022_ward16      | PAM   | O/O        |   10.28/10.88 |   110.0/110.8 |      +5.8% |
| argyll_bute_2017_ward6         | Cast  | O/O        |   16.05/15.54 |   110.5/147.5 |      -3.2% |
| argyll_bute_2017_ward6         | PAM   | O/O        |   16.05/15.28 |   110.0/110.9 |      -4.8% |
| clackmannanshire_2017_ward5    | Cast  | O/O        |    9.44/10.16 |   109.8/139.5 |      +7.6% |
| clackmannanshire_2017_ward5    | PAM   | O/O        |     9.34/9.85 |   110.2/109.4 |      +5.5% |
| dumgal_2012_ward8              | Cast  | O/O        |    9.19/14.14 |   110.8/179.9 |     +53.9% |
| dumgal_2012_ward8              | PAM   | O/O        |     9.32/9.00 |   111.9/114.7 |      -3.4% |
| east_dunbartonshire_2022_ward5 | Cast  | O/O        |   19.14/23.04 |   111.2/187.8 |     +20.4% |
| east_dunbartonshire_2022_ward5 | PAM   | O/O        |   19.07/20.47 |   110.7/110.9 |      +7.3% |
| eilean_siar_2017_ward9         | Cast  | O/O        | 141.87/135.20 |   145.4/197.3 |      -4.7% |
| eilean_siar_2017_ward9         | PAM   | O/O        | 141.45/134.79 |   147.4/149.9 |      -4.7% |
| falkirk_2022_ward1             | Cast  | O/O        |   28.14/27.46 |   113.6/206.2 |      -2.4% |
| falkirk_2022_ward1             | PAM   | O/O        |   28.12/28.49 |   116.0/117.2 |      +1.3% |
| highland_2022_thurso           | Cast  | O/O        |  96.70/126.86 |   129.6/325.8 |     +31.2% |
| highland_2022_thurso           | PAM   | O/O        |  95.54/123.48 |   130.3/136.1 |     +29.2% |
| inverclyde_2017_ward3          | Cast  | O/O        |     6.99/4.18 |   104.9/113.6 |     -40.3% |
| inverclyde_2017_ward3          | PAM   | O/O        |     6.92/3.38 |    105.6/98.6 |     -51.2% |
| sc_borders_2012_ward4          | Cast  | O/O        |   82.40/85.67 |   127.6/266.0 |      +4.0% |
| sc_borders_2012_ward4          | PAM   | O/O        |   82.37/80.01 |   128.1/128.7 |      -2.9% |

### Head-to-head by election

| Election                       | Start | Status C/W | Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | -----------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | Cast  | O/O        |    5.33/5.64 |   105.7/171.4 |      +5.7% |
| aberdeenshire_2022_ward16      | PAM   | O/O        |    5.32/5.25 |   109.7/111.0 |      -1.2% |
| argyll_bute_2017_ward6         | Cast  | O/O        |  12.05/11.21 |   119.3/147.5 |      -7.0% |
| argyll_bute_2017_ward6         | PAM   | O/O        |  11.98/10.93 |   118.4/116.7 |      -8.8% |
| clackmannanshire_2017_ward5    | Cast  | O/O        |    5.33/5.95 |   109.6/138.7 |     +11.7% |
| clackmannanshire_2017_ward5    | PAM   | O/O        |    5.29/5.75 |   108.1/108.1 |      +8.6% |
| dumgal_2012_ward8              | Cast  | O/O        |    7.78/7.25 |   110.6/179.8 |      -6.9% |
| dumgal_2012_ward8              | PAM   | O/O        |    7.84/6.58 |   110.5/107.4 |     -16.0% |
| east_dunbartonshire_2022_ward5 | Cast  | O/O        |    7.15/7.51 |   112.1/189.2 |      +5.0% |
| east_dunbartonshire_2022_ward5 | PAM   | O/O        |    7.14/7.15 |   112.7/107.8 |      +0.2% |
| eilean_siar_2017_ward9         | Cast  | O/O        |  47.65/43.63 |   125.8/198.2 |      -8.4% |
| eilean_siar_2017_ward9         | PAM   | O/O        |  47.53/47.01 |   130.6/132.4 |      -1.1% |
| falkirk_2022_ward1             | Cast  | O/O        |  11.99/13.65 |   122.0/207.7 |     +13.9% |
| falkirk_2022_ward1             | PAM   | O/O        |  11.98/13.22 |   124.4/123.5 |     +10.4% |
| highland_2022_thurso           | Cast  | O/O        |  41.65/27.17 |   138.1/327.7 |     -34.8% |
| highland_2022_thurso           | PAM   | O/O        |  41.29/26.29 |   138.7/129.0 |     -36.3% |
| inverclyde_2017_ward3          | Cast  | O/O        |    6.23/4.95 |   107.1/112.8 |     -20.5% |
| inverclyde_2017_ward3          | PAM   | O/O        |    6.26/4.23 |   107.1/107.5 |     -32.5% |
| sc_borders_2012_ward4          | Cast  | O/O        |  33.34/22.06 |   132.8/266.1 |     -33.8% |
| sc_borders_2012_ward4          | PAM   | O/O        |  33.36/22.84 |   133.9/127.0 |     -31.5% |

## Cast-ballot target

| Metric | Start | Solved C/W | Faster | Time C/W (s) | Time delta | RSS delta |
| ------ | ----- | ---------: | -----: | -----------: | ---------: | --------: |
| Borda  | PAM   |      10/10 |   0/10 |    7.42/7.70 |      +4.6% |     +0.9% |
| H2H    | PAM   |      10/10 |   2/10 |    6.95/7.11 |      +3.4% |     +1.3% |

Only PAM starts were tested for this target. They did not improve median time or peak memory;
all cold and warm runs already finished within the original one-minute limit.

### Borda by election

| Election                       | Start | Status C/W | Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | -----------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | PAM   | O/O        |    4.78/5.15 |   568.2/567.1 |      +7.7% |
| argyll_bute_2017_ward6         | PAM   | O/O        |    4.25/4.57 |   503.2/507.3 |      +7.6% |
| clackmannanshire_2017_ward5    | PAM   | O/O        |    3.93/4.03 |   432.7/434.6 |      +2.7% |
| dumgal_2012_ward8              | PAM   | O/O        |    6.86/6.96 |   650.6/657.3 |      +1.4% |
| east_dunbartonshire_2022_ward5 | PAM   | O/O        |    7.99/8.44 |   722.2/731.5 |      +5.6% |
| eilean_siar_2017_ward9         | PAM   | O/O        |  22.98/23.81 |  977.1/1052.1 |      +3.6% |
| falkirk_2022_ward1             | PAM   | O/O        |  22.94/27.23 | 1086.9/1106.7 |     +18.7% |
| highland_2022_thurso           | PAM   | O/O        |  35.15/36.01 | 1584.2/1588.0 |      +2.4% |
| inverclyde_2017_ward3          | PAM   | O/O        |    1.73/1.86 |   293.4/292.7 |      +7.9% |
| sc_borders_2012_ward4          | PAM   | O/O        |  20.79/21.05 | 1075.9/1086.4 |      +1.2% |

### Head-to-head by election

| Election                       | Start | Status C/W | Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | -----------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | PAM   | O/O        |    4.86/5.26 |   565.7/570.4 |      +8.2% |
| argyll_bute_2017_ward6         | PAM   | O/O        |    4.18/4.84 |   501.5/508.8 |     +15.6% |
| clackmannanshire_2017_ward5    | PAM   | O/O        |    3.45/3.67 |   431.4/434.2 |      +6.2% |
| dumgal_2012_ward8              | PAM   | O/O        |    6.42/6.53 |   643.7/659.3 |      +1.7% |
| east_dunbartonshire_2022_ward5 | PAM   | O/O        |    7.48/7.69 |   710.7/723.6 |      +2.8% |
| eilean_siar_2017_ward9         | PAM   | O/O        |  13.27/13.80 |   802.9/807.0 |      +4.0% |
| falkirk_2022_ward1             | PAM   | O/O        |  30.63/26.36 | 1063.5/1120.7 |     -13.9% |
| highland_2022_thurso           | PAM   | O/O        |  36.30/36.54 | 1582.0/1601.0 |      +0.7% |
| inverclyde_2017_ward3          | PAM   | O/O        |    1.67/1.80 |   290.8/292.9 |      +7.3% |
| sc_borders_2012_ward4          | PAM   | O/O        |  29.19/23.60 | 1280.3/1308.5 |     -19.2% |

## Starting from an exact target solution

I also supplied a verified globally optimal solution to the target model itself, including all
auxiliary variables. This gives Gurobi the optimal incumbent, but no optimality certificate or
fixed variables: it still has to establish the lower bound. Time includes loading the solution, but
excludes the earlier work of finding and verifying it.

These results combine the earlier completed runs with the one-hour extension, using the same cold
baseline as the cast-ballot-start experiment. All 37 eligible exact-start runs reached OPTIMAL at
the benchmark's 0.01% relative-gap tolerance. Runs used two clusters, one thread, Seed=0, and
Gurobi 12.0.3.

| Target     | Metric | Tested | Solved C/W | Faster |  Time C/W (s) | Time delta | RSS delta |
| ---------- | ------ | -----: | ---------: | -----: | ------------: | ---------: | --------: |
| Coordinate | Borda  |     10 |      10/10 |   5/10 |   82.44/23.17 |      -4.0% |     -0.8% |
| Coordinate | H2H    |      7 |        7/7 |    4/7 | 244.40/230.39 |      -5.7% |     +2.7% |
| All-ballot | Borda  |     10 |      10/10 |   5/10 |   17.60/19.48 |      +1.2% |     +1.9% |
| All-ballot | H2H    |     10 |      10/10 |   6/10 |     9.88/9.18 |      -2.8% |     -2.4% |

Even providing the optimum did not consistently shorten the run, and typical memory use stayed
close to cold-run levels. Individual effects were much larger: Borda coordinate time fell from
94.25 to 10.88 seconds for `dumgal_2012_ward8`, but rose from 383.68 to 787.32 seconds for
`highland_2022_thurso`. This supports the explanation that proving the bound remains difficult
after finding the best centers. These are single runs, so small changes do not establish a
reliable speedup.

The three coordinate H2H cases below had no verified optimum available and were excluded from
this experiment. The exact-start results therefore do not tell us whether such starts would
help those unresolved cases. Exact starts were not tested for the cast-ballot target.

Here W means an exact-solution start; O means OPTIMAL at the stated tolerance.

### Coordinate Borda by election: exact start

| Election                       | Start | Status C/W |  Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | ------------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | Exact | O/O        |   10.45/19.59 |   114.9/119.4 |     +87.4% |
| argyll_bute_2017_ward6         | Exact | O/O        |   54.97/22.58 |   118.7/114.9 |     -58.9% |
| clackmannanshire_2017_ward5    | Exact | O/O        |   17.30/17.74 |   112.0/115.8 |      +2.5% |
| dumgal_2012_ward8              | Exact | O/O        |   94.25/10.88 |   221.9/113.5 |     -88.5% |
| east_dunbartonshire_2022_ward5 | Exact | O/O        |   98.47/23.76 |   144.1/118.7 |     -75.9% |
| eilean_siar_2017_ward9         | Exact | O/O        | 487.22/537.82 |   269.7/262.3 |     +10.4% |
| falkirk_2022_ward1             | Exact | O/O        |   70.64/61.90 |   124.9/125.3 |     -12.4% |
| highland_2022_thurso           | Exact | O/O        | 383.68/787.32 |   211.9/251.6 |    +105.2% |
| inverclyde_2017_ward3          | Exact | O/O        |     3.98/5.20 |   102.1/102.2 |     +30.6% |
| sc_borders_2012_ward4          | Exact | O/O        | 455.10/407.31 |   220.6/216.8 |     -10.5% |

### Coordinate head-to-head by election: exact start

| Election                       | Start | Status C/W |   Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | -------------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | Exact | O/O        |  161.82/135.24 |   139.9/135.3 |     -16.4% |
| argyll_bute_2017_ward6         | Exact | O/O        |  625.60/724.55 |   216.7/232.9 |     +15.8% |
| clackmannanshire_2017_ward5    | Exact | O/O        |  135.48/152.83 |   129.5/135.4 |     +12.8% |
| dumgal_2012_ward8              | Exact | O/O        |  244.40/230.39 |   153.1/158.0 |      -5.7% |
| east_dunbartonshire_2022_ward5 | Exact | O/O        |  530.88/376.66 |   182.0/179.7 |     -29.1% |
| falkirk_2022_ward1             | Exact | O/O        | 1458.30/565.47 |   309.7/259.2 |     -61.2% |
| inverclyde_2017_ward3          | Exact | O/O        |    13.93/41.73 |   117.9/121.2 |    +199.6% |

### All-ballot Borda by election: exact start

| Election                       | Start | Status C/W |  Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | ------------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | Exact | O/O        |   10.22/10.77 |   109.1/111.9 |      +5.3% |
| argyll_bute_2017_ward6         | Exact | O/O        |   16.05/15.14 |   110.5/112.3 |      -5.7% |
| clackmannanshire_2017_ward5    | Exact | O/O        |     9.44/9.79 |   109.8/108.2 |      +3.6% |
| dumgal_2012_ward8              | Exact | O/O        |    9.19/12.98 |   110.8/112.0 |     +41.3% |
| east_dunbartonshire_2022_ward5 | Exact | O/O        |   19.14/23.83 |   111.2/111.9 |     +24.5% |
| eilean_siar_2017_ward9         | Exact | O/O        | 141.87/133.45 |   145.4/148.7 |      -5.9% |
| falkirk_2022_ward1             | Exact | O/O        |   28.14/26.94 |   113.6/116.3 |      -4.2% |
| highland_2022_thurso           | Exact | O/O        |  96.70/122.72 |   129.6/134.7 |     +26.9% |
| inverclyde_2017_ward3          | Exact | O/O        |     6.99/6.57 |   104.9/108.1 |      -6.1% |
| sc_borders_2012_ward4          | Exact | O/O        |   82.40/81.47 |   127.6/125.7 |      -1.1% |

### All-ballot head-to-head by election: exact start

| Election                       | Start | Status C/W | Time C/W (s) | RSS C/W (MiB) | Time delta |
| ------------------------------ | ----- | ---------- | -----------: | ------------: | ---------: |
| aberdeenshire_2022_ward16      | Exact | O/O        |    5.33/5.23 |   105.7/110.3 |      -1.9% |
| argyll_bute_2017_ward6         | Exact | O/O        |  12.05/10.87 |   119.3/115.3 |      -9.8% |
| clackmannanshire_2017_ward5    | Exact | O/O        |    5.33/5.69 |   109.6/107.8 |      +6.8% |
| dumgal_2012_ward8              | Exact | O/O        |    7.78/7.50 |   110.6/110.8 |      -3.7% |
| east_dunbartonshire_2022_ward5 | Exact | O/O        |    7.15/7.28 |   112.1/108.6 |      +1.8% |
| eilean_siar_2017_ward9         | Exact | O/O        |  47.65/48.36 |   125.8/133.1 |      +1.5% |
| falkirk_2022_ward1             | Exact | O/O        |  11.99/12.50 |   122.0/120.0 |      +4.3% |
| highland_2022_thurso           | Exact | O/O        |  41.65/26.28 |   138.1/127.7 |     -36.9% |
| inverclyde_2017_ward3          | Exact | O/O        |    6.23/3.51 |   107.1/103.3 |     -43.7% |
| sc_borders_2012_ward4          | Exact | O/O        |  33.34/22.08 |   132.8/125.6 |     -33.8% |

## Coordinate H2H: what did not finish in an hour on my machine

These three elections reached the one-hour limit on my machine. The entries below are final relative
gaps (%):

| Election               | Gap C/W: cast-ballot start | Gap C/W: PAM start |
| ---------------------- | -------------------------: | -----------------: |
| eilean_siar_2017_ward9 |                31.04/29.23 |        30.92/32.66 |
| highland_2022_thurso   |                18.42/17.22 |        18.28/17.26 |
| sc_borders_2012_ward4  |                24.76/23.28 |        24.64/25.82 |
