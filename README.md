# CS4100 SAT solver: DPLL baseline and CDCL upgrade

Two solvers with the same interface and output, so results compare row for row.

- `dpll.py`: basic DPLL with unit propagation, pure-literal elimination,
and branching on the first unassigned variable (Davis & Putnam 1960;
Davis, Logemann & Loveland 1962). No clause learning or heuristics.
- `cdcl.py`: conflict-driven clause learning built on the same parser.

| CDCL piece | Source |
| --- | --- |
| Clause learning, non-chronological backjumping | GRASP: Marques-Silva & Sakallah, ICCAD 1996 |
| First-UIP learning scheme | Zhang, Madigan, Moskewicz & Malik, ICCAD 2001 |
| Two watched literals, VSIDS branching | Chaff: Moskewicz et al., DAC 2001 |
| Restarts | Gomes, Selman & Kautz, AAAI 1998 |
| Luby restart schedule | Luby, Sinclair & Zuckerman 1993; Huang, IJCAI 2007 |
| Phase saving | Pipatsrisawat & Darwiche, SAT 2007 |
| Defaults (decay 0.95, restart unit 100, polarity False) | MiniSat 2.2 (Eén & Sörensson, SAT 2003) |

My own simplifications: VSIDS picks the next variable with a linear scan  
instead of a heap (fine for 200 variables or fewer), and learned clauses  
are never deleted.

## Run it

```
python3 dpll.py Benchmarks/uf20-91/uf20-01.cnf        # one instance
python3 cdcl.py Benchmarks/uf20-91 > results.csv      # whole folder
```

Each prints one CSV row per instance: `file,result,decisions,conflicts,seconds`.
A total-time line goes to stderr. `cdcl.py` also checks every SAT model
against the original clauses and exits with an error if one is wrong.

## Results

- `results/*.csv`, `results/summary.csv`: DPLL
- `results/cdcl/*.csv`, `results/cdcl/summary.csv`: CDCL

Both were run with 7 instances in parallel (`xargs -P 7`), so times are
per-instance wall clock under that load.

## From Python

```
from cdcl import solve      # or: from dpll import solve
model, seconds = solve("Benchmarks/uf20-91/uf20-01.cnf")  # model is None if UNSAT
```
