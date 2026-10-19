"""Gỡ bridge COWORK khỏi bản Brain STAGING (rollback cục bộ).

    .venv/bin/python scripts/remove_bridge.py brain-staging
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_bridge import MARKER  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    backend = Path(argv[0]).resolve() / "backend"
    main_py = backend / "app" / "main.py"
    if main_py.is_file():
        lines = [l for l in main_py.read_text(encoding="utf-8").splitlines(True)
                 if MARKER not in l]
        main_py.write_text("".join(lines), encoding="utf-8")
        print("→ Đã gỡ dòng bridge khỏi app/main.py.")
    target = backend / "app" / "api" / "cowork_bridge.py"
    if target.exists():
        target.unlink()
        print("→ Đã xoá app/api/cowork_bridge.py.")
    print("Rollback staging hoàn tất. Với production, dùng git revert + restart theo ROLLBACK.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
