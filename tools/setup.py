"""在本机输入并加密图床 Token；不连接网络、不改 Typora 设置。"""
import getpass
import json
from pathlib import Path
import sys

from upload import CONFIG, protect_token, validate_base_url


def main():
    print("请输入已部署的图床信息。密钥只保存在本机，不发到聊天里。")
    base_url = validate_base_url(input("图床根地址（https://...）："))
    channel = input("S3 渠道名称（只有一个 S3 渠道时可留空）：").strip()
    token = getpass.getpass("图床 API Token（只需要 upload 权限，输入不显示）：").strip()
    if not token or any(character in token for character in "\r\n"):
        raise ValueError("Token 不能为空或包含换行。")
    config = {"baseUrl": base_url, "channelName": channel, "uploadFolder": "typora",
              "jpgQuality": 85, "tokenDpapi": protect_token(token)}
    if CONFIG.exists():
        backup = Path(str(CONFIG) + ".previous")
        if backup.exists():
            raise ValueError("已有上次配置备份，请先核对 config.json.previous，再重新配置。")
        backup.write_bytes(CONFIG.read_bytes())
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("图床配置已保存。Token 使用 Windows DPAPI 加密。")
    print("Typora 自定义命令：")
    print(f'"{sys.executable}" "{CONFIG.parent / "upload.py"}"')


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyboardInterrupt) as error:
        print("配置未完成：" + str(error), file=sys.stderr)
        sys.exit(1)
