"""Áp dụng bridge COWORK vào bản Brain STAGING (không bao giờ production).

    .venv/bin/python scripts/apply_bridge.py brain-staging

Thao tác:
1. Sao tệp `brain-bridge/cowork_bridge.py` → `<staging>/backend/app/api/`.
2. Chèn import + include_router vào `app/main.py` (idempotent, có marker).
3. Kiểm tra import bằng Python của staging.

Không sửa `vip-brain.db`, không sửa frontend, không đổi cổng Brain production.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NGUON = ROOT / "brain-bridge" / "cowork_bridge.py"
MARKER = "# COWORK BRIDGE"


def patch_main(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print("→ main.py đã có bridge, bỏ qua chèn.")
        return False
    anchor_import = "from .api import router as api_router\n"
    if anchor_import not in text:
        raise SystemExit("Không tìm thấy dòng import api_router trong app/main.py")
    text = text.replace(
        anchor_import,
        anchor_import + "from .api import cowork_bridge  " + MARKER + "\n",
        1,
    )
    anchor_include = 'app.include_router(api_router, prefix="/api")\n'
    if anchor_include not in text:
        raise SystemExit("Không tìm thấy dòng include api_router trong app/main.py")
    pos = text.find(anchor_include)
    line_start = text.rfind("\n", 0, pos) + 1
    indent = text[line_start:pos]  # giữ đúng thụt lề của dòng gốc (trong tao_app)
    text = text.replace(
        anchor_include,
        anchor_include + indent + "app.include_router(cowork_bridge.router)  " + MARKER + "\n",
        1,
    )
    path.write_text(text, encoding="utf-8")
    print("→ Đã chèn bridge vào app/main.py (giữ thụt lề).")
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    stg = Path(argv[0]).resolve()
    backend = stg / "backend"
    if not (backend / "app" / "main.py").is_file():
        raise SystemExit(f"Không thấy backend Brain staging tại {backend}")
    if not NGUON.is_file():
        raise SystemExit(f"Không thấy {NGUON}")
    shutil.copy2(NGUON, backend / "app" / "api" / "cowork_bridge.py")
    print("→ Đã sao tệp app/api/cowork_bridge.py.")
    patch_main(backend / "app" / "main.py")
    venv_py = backend / ".venv" / "bin" / "python"
    if venv_py.is_file():
        r = subprocess.run([str(venv_py), "-c", "import app.main; print('import ok')"],
                           cwd=str(backend), capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout)
            print(r.stderr)
            raise SystemExit("Import Brain staging THẤT BẠI sau khi vá.")
        print("→ " + r.stdout.strip())
    (stg / ".cowork-bridge.json").write_text(json.dumps({
        "applied": True,
        "module": "app/api/cowork_bridge.py",
        "routes": ["/cowork/vao", "/api/cowork/thu-hoi", "/api/cowork/suc-khoe"],
        "featureFlag": "COWORK_BRIDGE_BAT",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
