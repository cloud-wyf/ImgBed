"""由用户在本机窗口查看图床后台登录信息。"""
import json
from pathlib import Path
from upload import protect_token

credentials = json.loads(protect_token((Path(__file__).resolve().parent / "backend-credentials.dpapi").read_text(encoding="ascii"), decrypt=True))
print("后台地址：https://slanwyf-imgbed.pages.dev/dashboard")
print("用户名：" + credentials["username"])
print("后台密码：" + credentials["password"])
print("首页上传密码：" + credentials["authCode"])
print("请勿将以上密码发送到聊天或分享截图。")
