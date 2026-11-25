#!/usr/bin/env python3
"""DPLL SAT solver (baseline).

Usage:
    python3 dpll.py file.cnf # solve one instance
    python3 dpll.py uf20-91/ # solve every .cnf in a folder
"""

import os
import sys
import time

stats = {"decisions": 0, "conflicts": 0}

def parse(path):
    """Read a SATLIB DIMACS file (one clause per line) into a list of clauses."""
    clauses = []
    for line in open(path):
        tokens = line.split()
        if not tokens or tokens[0] in ("c", "p"):
            continue
        if tokens[0] == "%":  # SATLIB end marker
            break
        clauses.append([int(t) for t in tokens if t != "0"])
    return clauses


def assign(clauses, lit):
    """Make literal true: drop satisfied clauses, remove the negative of the literal from the rest."""
    return [[l for l in c if l != -lit] for c in clauses if lit not in c]


def dpll(clauses, model):
    """Return a satisfying model (dict var -> bool), or None if UNSAT."""
    while True:
        if not clauses:
            return model
        if [] in clauses:
            stats["conflicts"] += 1
            return None

        # Find the first unit clause or pure literal.
        lit = next((c[0] for c in clauses if len(c) == 1), None) # only literal of the first clause that has exactly one literal left
        if lit is None: # if no unit clause, then check for pure literals
            lits = {l for c in clauses for l in c} # set of all literals in all clauses
            lit = next((l for l in lits if -l not in lits), None) # finds literal that doesn't have a negative counterpart
        if lit is None: # if no pure literal, then break and pick another branch
            break
        model = {**model, abs(lit): lit > 0} # assign the literal to the model
        clauses = assign(clauses, lit) # remove the satisfied clause and the negative of the literal from the remaining clauses

    # Branch on the first unassigned variable we see, trying True first.
    var = abs(clauses[0][0]) # get the first unassigned variable in the first clause
    stats["decisions"] += 1
    for lit in (var, -var): # try both True and False for the first unassigned variable
        result = dpll(assign(clauses, lit), {**model, var: lit > 0}) # assign the literal to the model and solve the remaining clauses
        if result is not None: # if the result is not None, then return the result
            return result # return the result, either a satisfying model or None
    return None # if no satisfying model, then return None


def solve(path):
    stats["decisions"] = stats["conflicts"] = 0
    start = time.time()
    model = dpll(parse(path), {}) # parse the clauses and solve them
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
        result = "SAT" if model is not None else "UNSAT"
        print(f"{os.path.basename(f)},{result},{stats['decisions']},{stats['conflicts']},{secs:.4f}")
    print(f"# {len(files)} instances, {total:.2f}s total", file=sys.stderr)
