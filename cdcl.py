#!/usr/bin/env python3
"""CDCL SAT solver (upgrade of the DPLL baseline).

Adds clause learning with non-chronological backjumping, two watched
literals, VSIDS branching, phase saving and Luby restarts.

Usage:
    python3 cdcl.py file.cnf # solve one instance
    python3 cdcl.py uf20-91/ # solve every .cnf in a folder
"""

import os
import sys
import time

from dpll import parse  # same SATLIB DIMACS reader as the baseline

stats = {"decisions": 0, "conflicts": 0}

DECAY = 0.95         # VSIDS activity decay per conflict (MiniSat 2.2 default)
RESTART_UNIT = 100   # conflicts per Luby unit (MiniSat 2.2 default)


def luby(i):
    """i-th term (from 0) of the Luby sequence 1,1,2,1,1,2,4,... (Luby, Sinclair & Zuckerman 1993)."""
    size, seq = 1, 0
    while size < i + 1: # find the smallest complete subsequence that contains index i
        seq += 1
        size = 2 * size + 1
    while size - 1 != i: # walk down into the half that holds i
        size = (size - 1) >> 1
        seq -= 1
        i %= size
    return 2 ** seq


class Solver:
    def __init__(self, clauses):
        self.n = max((abs(l) for c in clauses for l in c), default=0)
        self.val = {l: 0 for v in range(1, self.n + 1) for l in (v, -v)} # literal -> 1 true, -1 false, 0 unassigned
        self.watches = {l: [] for l in self.val} # literal -> clauses currently watching it
        self.level = [0] * (self.n + 1) # decision level each variable was assigned at
        self.reason = [None] * (self.n + 1) # clause that forced each variable (None for decisions)
        self.activity = [0.0] * (self.n + 1) # VSIDS score per variable
        self.phase = [False] * (self.n + 1) # saved polarity, starts False like MiniSat
        self.inc = 1.0 # how much one bump adds; grows instead of decaying every score
        self.trail = [] # assigned literals in order
        self.trail_lim = [] # where each decision level starts on the trail
        self.qhead = 0 # next trail literal to propagate
        self.clauses = clauses

    def enqueue(self, lit, reason):
        """Make literal true at the current decision level and remember why."""
        v = abs(lit)
        self.val[lit], self.val[-lit] = 1, -1
        self.level[v] = len(self.trail_lim)
        self.reason[v] = reason
        self.trail.append(lit)

    def propagate(self):
        """Unit propagation with two watched literals (Chaff, Moskewicz et al. 2001).
        Returns the conflicting clause, or None if no conflict."""
        val, watches, trail = self.val, self.watches, self.trail
        while self.qhead < len(trail):
            false_lit = -trail[self.qhead] # this literal just became false
            self.qhead += 1
            ws = watches[false_lit]
            watches[false_lit] = keep = [] # clauses that still watch it after this pass
            for k, c in enumerate(ws):
                if c[0] == false_lit: # keep the false watch in slot 1
                    c[0], c[1] = c[1], c[0]
                if val[c[0]] == 1: # other watch is true, so the clause is satisfied
                    keep.append(c)
                    continue
                for j in range(2, len(c)): # look for a non-false literal to watch instead
                    if val[c[j]] != -1:
                        c[1], c[j] = c[j], c[1]
                        watches[c[1]].append(c)
                        break
                else: # no replacement: the clause is unit or conflicting
                    keep.append(c)
                    if val[c[0]] == -1: # every literal is false, so this is a conflict
                        keep.extend(ws[k + 1:])
                        return c
                    self.enqueue(c[0], c) # only c[0] is left, so it is forced true
        return None

    def bump(self, v):
        """VSIDS: raise the activity of a variable involved in a conflict (Chaff 2001, MiniSat 2003)."""
        self.activity[v] += self.inc
        if self.activity[v] > 1e100: # rescale everything before floats overflow
            self.activity = [a * 1e-100 for a in self.activity]
            self.inc *= 1e-100

    def analyze(self, conflict):
        """1-UIP clause learning (GRASP, Marques-Silva & Sakallah 1996; Zhang et al. 2001).
        Resolve the conflict with reason clauses until one literal from the current
        level is left. Returns the learned clause and the level to backjump to."""
        cur = len(self.trail_lim)
        seen, learned = set(), [None] # slot 0 is saved for the UIP literal
        counter, lit, clause, i = 0, None, conflict, len(self.trail) - 1
        while True:
            for q in clause:
                v = abs(q)
                if q != lit and v not in seen and self.level[v] > 0: # skip the literal being resolved on and level-0 facts
                    seen.add(v)
                    self.bump(v)
                    if self.level[v] == cur: # current-level literals get resolved away
                        counter += 1
                    else: # earlier-level literals go into the learned clause
                        learned.append(q)
            while abs(self.trail[i]) not in seen: # most recent assigned literal we have seen
                i -= 1
            lit = self.trail[i]
            i -= 1
            counter -= 1
            if counter == 0: # lit is the first UIP
                break
            clause = self.reason[abs(lit)] # resolve on lit next
        learned[0] = -lit
        if len(learned) == 1: # a unit clause, so it holds at level 0
            return learned, 0
        k = max(range(1, len(learned)), key=lambda j: self.level[abs(learned[j])])
        learned[1], learned[k] = learned[k], learned[1] # watch the highest-level literal in slot 1
        return learned, self.level[abs(learned[1])]

    def backjump(self, lvl):
        """Non-chronological backtracking (GRASP 1996): undo every level above lvl.
        Saves each variable's last value for phase saving (Pipatsrisawat & Darwiche 2007)."""
        if len(self.trail_lim) <= lvl:
            return
        pos = self.trail_lim[lvl]
        for lit in self.trail[pos:]:
            v = abs(lit)
            self.phase[v] = lit > 0 # remember the polarity for the next time we branch on v
            self.val[lit] = self.val[-lit] = 0
            self.reason[v] = None
        del self.trail[pos:]
        del self.trail_lim[lvl:]
        self.qhead = pos

    def pick(self):
        """VSIDS branching: the unassigned variable with the highest activity (0 if none left).
        A linear scan instead of MiniSat's heap, which is fine for n <= 200."""
        val, act = self.val, self.activity
        return max((v for v in range(1, self.n + 1) if val[v] == 0), key=act.__getitem__, default=0)

    def solve(self):
        """Return a satisfying model (dict var -> bool), or None if UNSAT."""
        for c in self.clauses:
            c[:] = list(dict.fromkeys(c)) # drop repeated literals
            if any(-l in c for l in c): # tautology, always true, so skip it
                continue
            if not c: # empty clause can never be satisfied
                return None
            if len(c) == 1: # unit clause, assign it at level 0
                if self.val[c[0]] == -1:
                    return None
                if self.val[c[0]] == 0:
                    self.enqueue(c[0], None)
            else: # watch the first two literals
                self.watches[c[0]].append(c)
                self.watches[c[1]].append(c)

        restarts, since_restart = 0, 0
        while True:
            conflict = self.propagate()
            if conflict is not None:
                stats["conflicts"] += 1
                since_restart += 1
                if not self.trail_lim: # conflict with no decisions made, so UNSAT
                    return None
                learned, lvl = self.analyze(conflict)
                self.backjump(lvl) # jump back to where the learned clause becomes unit
                if len(learned) == 1:
                    self.enqueue(learned[0], None)
                else:
                    self.watches[learned[0]].append(learned)
                    self.watches[learned[1]].append(learned)
                    self.enqueue(learned[0], learned) # learned clause forces the UIP literal
                self.inc /= DECAY # newer conflicts count more (same as decaying old scores)
            elif since_restart >= RESTART_UNIT * luby(restarts):
                # Restart (Gomes, Selman & Kautz 1998) on the Luby schedule (Huang 2007, MiniSat 2.2):
                # drop all decisions but keep learned clauses, activities and saved phases.
                self.backjump(0)
                restarts += 1
                since_restart = 0
            else:
                var = self.pick()
                if var == 0: # every variable is assigned with no conflict, so SAT
                    return {v: self.val[v] == 1 for v in range(1, self.n + 1)}
                stats["decisions"] += 1
                self.trail_lim.append(len(self.trail)) # open a new decision level
                self.enqueue(var if self.phase[var] else -var, None)


def check(clauses, model):
    """True if every clause has at least one true literal under the model."""
    return all(any(model.get(abs(l)) == (l > 0) for l in c) for c in clauses)


def solve(path):
    stats["decisions"] = stats["conflicts"] = 0
    start = time.time()
    model = Solver(parse(path)).solve() # parse the clauses and solve them
    return model, time.time() - start


if __name__ == "__main__":
    target = sys.argv[1]
    if os.path.isdir(target):
        files = sorted(os.path.join(target, f) for f in os.listdir(target) if f.endswith(".cnf"))
    else:
        files = [target]

    total = 0.0
    print("file,result,decisions,conflicts,seconds")
    for f in files:
        model, secs = solve(f)
        total += secs
        if model is not None and not check(parse(f), model): # catch a solver bug instead of reporting a wrong SAT
            sys.exit(f"{f}: returned model does not satisfy every clause")
        result = "SAT" if model is not None else "UNSAT"
        print(f"{os.path.basename(f)},{result},{stats['decisions']},{stats['conflicts']},{secs:.4f}")
    print(f"# {len(files)} instances, {total:.2f}s total", file=sys.stderr)
