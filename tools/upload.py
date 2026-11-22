"""Typora 图片上传：本地转换 WebP，使用图床上传 Token，逐行返回链接。"""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

from deduplicate import RemoteVerifier, reuse_or_upload
from local_index import UploadIndex, local_lock

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
MAX_FILE_BYTES = 90 * 1024 * 1024


def protect_token(value, decrypt=False):
    """使用 Windows DPAPI；密文仅供当前 Windows 用户在本机解密。"""
    if os.name != "nt":
        raise RuntimeError("此凭据配置仅支持 Windows。")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    raw = base64.b64decode(value, validate=True) if decrypt else value.encode("utf-8")
    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source, target = Blob(len(raw), buffer), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        result = ctypes.string_at(target.data, target.size)
        return result.decode("utf-8") if decrypt else base64.b64encode(result).decode("ascii")
    finally:
        kernel.LocalFree(target.data)


def validate_base_url(value):
    value = value.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path):
        raise ValueError("图床网址必须是 HTTPS 根地址，例如 https://img.example.com。")
    return value


def prepare_image(path, quality=85):
    """原图不改动；保留动图，PNG 无损，JPG 有损，只采用更小的结果。"""
    if not path.is_file():
        raise ValueError("找不到需要上传的本地图片。")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("单张图片超过 90 MB，请先缩小图片。")
    original = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png"}:
        return original, suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(original)) as image:
        if getattr(image, "is_animated", False):
            return original, suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        lossless = image.format == "PNG"
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
        output = io.BytesIO()
        options = {"lossless": lossless, "quality": quality, "method": 4}
        if image.info.get("icc_profile"):
            options["icc_profile"] = image.info["icc_profile"]
        image.save(output, format="WEBP", **options)
        converted = output.getvalue()
    if len(converted) < len(original):
        return converted, ".webp", "image/webp"
    return original, suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def upload_one(path, config, token, opener=None, *, index=None, verifier=None):
    payload, suffix, mime = prepare_image(path, int(config.get("jpgQuality", 85)))
    if index is None:
        with local_lock(wait_seconds=120), UploadIndex() as stored_index:
            return upload_prepared(payload, suffix, mime, config, token, opener, stored_index,
                verifier or RemoteVerifier(config))
    return upload_prepared(payload, suffix, mime, config, token, opener, index, verifier or RemoteVerifier(config))


def upload_prepared(payload, suffix, mime, config, token, opener, index, verifier):
    def send():
        return send_image(payload, suffix, mime, config, token, opener)
    url, reused = reuse_or_upload(payload, mime, config, index, verifier, send)
    if reused:
        print("相同图片已存在，复用原链接。", file=sys.stderr)
    return url


def send_image(payload, suffix, mime, config, token, opener=None):
    filename = hashlib.sha256(payload).hexdigest()[:16] + suffix
    boundary = "TyporaImgBed" + uuid.uuid4().hex
    prefix = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
              f"filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n").encode("ascii")
    body = prefix + payload + f"\r\n--{boundary}--\r\n".encode("ascii")
    folder = str(config.get("uploadFolder", "typora")).strip("/")
    params = {"uploadChannel": "s3", "returnFormat": "full", "responseFormat": "object",
              "autoRetry": "false", "uploadFolder": folder}
    if config.get("channelName"):
        params["channelName"] = config["channelName"]
    base_url = config["baseUrl"]
    request = urllib.request.Request(base_url + "/upload?" + urllib.parse.urlencode(params),
        data=body, headers={"Authorization": "Bearer " + token,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Accept": "application/json", "User-Agent": "TyporaImgBed/1.0"}, method="POST")
    opener = opener or urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=90) as response:
        result = json.loads(response.read(1024 * 1024))
    if isinstance(result, list):
        result = result[0] if result else {}
    if not isinstance(result, dict) or not (result.get("publicUrl") or result.get("src")):
        raise ValueError("图床未返回有效图片链接，请检查上传渠道和 Token 权限。")
    url = urllib.parse.urljoin(base_url + "/", result.get("publicUrl") or result["src"])
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("图床返回的图片链接不是有效的 HTTPS 地址。")
    print(f"已上传 {len(payload):,} 字节，格式 {suffix}。", file=sys.stderr)
    return url


def main(paths):
    if not paths:
        raise ValueError("请通过 Typora 调用上传程序，并传入图片路径。")
    if not CONFIG.is_file():
        raise ValueError("尚未配置图床，请先运行 setup.cmd。")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["baseUrl"] = validate_base_url(config["baseUrl"])
    token = protect_token(config["tokenDpapi"], decrypt=True)
    with local_lock(wait_seconds=120), UploadIndex() as index:
        verifier = RemoteVerifier(config)
        urls = [upload_one(Path(path), config, token, index=index, verifier=verifier) for path in paths]
    # 全部成功后才输出 URL，供 Typora 按顺序替换；错误信息只能写 stderr。
    print("\n".join(urls))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        main(sys.argv[1:])
    except urllib.error.HTTPError as error:
        print(f"上传失败：HTTP {error.code}。请检查图床地址、Token 和 S3 渠道。", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError:
        print("上传失败：无法连接图床，请检查网络、代理和证书。", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # 不输出图床响应、请求头或凭据。
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print("上传失败：" + message, file=sys.stderr)
        sys.exit(1)
