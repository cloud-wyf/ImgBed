"""本机接收 B2 图床专用密钥，以 DPAPI 加密保存，不显示密钥内容。"""
import getpass
import json
from pathlib import Path

from upload import protect_token

print("在 B2 的已准备表单中创建 cloudflare-imgbed 密钥。")
print("范围应是 slanwyf-typora-imgbed，类型 Read and Write。")
key_id = getpass.getpass("粘贴 keyID（输入隐藏）：").strip()
application_key = getpass.getpass("粘贴 applicationKey（输入隐藏）：").strip()
if not key_id or not application_key:
    raise SystemExit("密钥不能为空。")
target = Path(__file__).resolve().parent / "b2-credentials.dpapi"
if target.exists():
    raise SystemExit("已存在密钥文件，停止以避免覆盖。")
target.write_text(protect_token(json.dumps({"keyId": key_id, "applicationKey": application_key})), encoding="ascii")
print("密钥已加密保存在 D 盘。可以关闭窗口并告诉我已保存。")
