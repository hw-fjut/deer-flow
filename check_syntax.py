import ast
import pathlib
import sys

root = pathlib.Path(r"e:\sourceCode\deer-flow\backend\packages\harness\deerflow\devflow")
ok = True
for p in root.rglob("*.py"):
    try:
        ast.parse(p.read_text(encoding="utf-8"), str(p))
        print(f"OK   {p.relative_to(root)}")
    except SyntaxError as e:
        ok = False
        print(f"FAIL {p.relative_to(root)}: {e}")
print("ALL OK" if ok else "SYNTAX ERRORS FOUND")
sys.exit(0 if ok else 1)
