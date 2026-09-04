# -*- coding: utf-8 -*-
import subprocess, sys, threading, io, os
sys.stdout = io.TextIOWrap(sys.stdout.buffer if hasattr(sys.stdout,'buffer') else sys.stdout, encoding='utf-8')
os.chdir(r"D:\c\ai-daily-puish")

suites = [
    ("test_all.py", None), ("test_practical.py", None),
    ("comprehensive_test.py", None), ("enterprise_test.py", None),
]
for name, _ in suites:
    r = subprocess.run(["python", name], capture_output=True)
    out = r.stdout.decode("utf-8", "replace")
    lines = [l.strip()[ :90] for l in out.splitlines()
             if any(k in line for line, k in [(l,"通过率"),(l,"总计"),(l,"通过:")])][-2:]
    print(name, "exit=", r.returncode)
    for x in lines: print("   ", x)
