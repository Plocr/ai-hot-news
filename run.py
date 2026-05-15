"""运行完整 pipeline：热榜 → RSS → 生成"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
STEPS = [
    ("1/3: Fetch platform hotlists", ["src/fetcher.py", "--hotlist"]),
    ("2/3: Fetch RSS feeds", ["src/fetcher.py"]),
    ("3/3: Generate static page", ["src/generator.py"]),
]

if __name__ == "__main__":
    for label, cmd in STEPS:
        print()
        print("=" * 40)
        print(label)
        print("=" * 40)
        r = subprocess.run([sys.executable] + cmd, cwd=ROOT)
        if r.returncode != 0:
            print(f"Failed: {label}")
            sys.exit(1)

    print()
    print("Done! Output: docs/index.html")
