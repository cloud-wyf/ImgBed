"""预览或应用 Typora 图片上传设置；应用前要求关闭 Typora 并保留备份。"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from upload import CONFIG, validate_base_url

PROFILE = Path(os.environ["APPDATA"]) / "Typora/profile.data"
BACKUPS = Path(__file__).resolve().parent / "backups"


def main(apply=False):
    original = PROFILE.read_bytes()
    profile = json.loads(bytes.fromhex(original.decode("ascii").strip()).decode("utf-8"))
    command = f'"{sys.executable}" "{Path(__file__).resolve().parent / "upload.py"}"'
    changes = {"image_uploader": "custom", "custom_image_uploader": command,
               "image_save_location": "upload", "no_image_move_for_local": False,
               "apply_image_move_for_web": False}
    print(json.dumps({"status": "preview", "settings": changes}, ensure_ascii=False, indent=2))
    if not apply:
        return
    if not CONFIG.exists():
        raise ValueError("请先配置并验证真实图床。")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    validate_base_url(config["baseUrl"])
    running = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "if (Get-Process -Name Typora -ErrorAction SilentlyContinue) { exit 1 }"], capture_output=True)
    if running.returncode:
        raise ValueError("Typora 正在运行。请保存文档并退出 Typora，然后再应用设置。")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / ("profile-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".data")
    backup.write_bytes(original)
    profile.update(changes)
    encoded = json.dumps(profile, ensure_ascii=False, separators=(",", ":")).encode("utf-8").hex().encode("ascii")
    if PROFILE.read_bytes() != original:
        raise ValueError("Typora 配置发生变化，已停止写入；备份已保留。")
    PROFILE.write_bytes(encoded)
    verified = json.loads(bytes.fromhex(PROFILE.read_text(encoding="ascii")).decode("utf-8"))
    if any(verified.get(key) != value for key, value in changes.items()):
        PROFILE.write_bytes(original)
        raise ValueError("写入验证失败，已恢复原设置。")
    print(json.dumps({"status": "applied", "backup": str(backup)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    try:
        main(arguments.apply)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
