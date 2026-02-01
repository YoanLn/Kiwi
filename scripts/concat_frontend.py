from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
OUT_PATH = FRONTEND / "frontend_concat.txt"

EXCLUDE_DIRS = {"node_modules", "dist", "build", ".git", ".vite"}
EXCLUDE_NAME = {
    "frontend_concat.txt",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
}
EXCLUDE_CONFIG_SUFFIXES = (".ts", ".js", ".json")


def should_exclude_file(path: Path) -> bool:
    name = path.name
    if name in EXCLUDE_NAME:
        return True
    if "config" in name.lower() and name.lower().endswith(EXCLUDE_CONFIG_SUFFIXES):
        return True
    return False


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            p = Path(dirpath) / fname
            if should_exclude_file(p):
                continue
            yield p


def main() -> int:
    if not FRONTEND.exists():
        raise SystemExit(f"frontend folder not found: {FRONTEND}")

    files = sorted(iter_files(FRONTEND), key=lambda p: str(p).lower())

    OUT_PATH.write_text("", encoding="utf-8")
    with OUT_PATH.open("a", encoding="utf-8", newline="\n") as out:
        for f in files:
            rel = f.relative_to(FRONTEND).as_posix()
            out.write(f"# === FILE: {rel} ===\n")
            try:
                out.write(f.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                out.write(f.read_text(encoding="utf-8", errors="replace"))
            out.write("\n\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
