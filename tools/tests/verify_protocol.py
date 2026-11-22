"""只使用本地模拟服务器验证上传协议，不上传真实文件到云端。"""
import contextlib
from email.parser import BytesParser
from email.policy import default
import io
import json
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent / "artifacts"
ROOT.mkdir(exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import upload as uploader
from local_index import UploadIndex
uploader.UploadIndex = lambda: UploadIndex(":memory:")

for name in ["upload.py", "setup.py"]:
    path = uploader.ROOT / name
    compile(path.read_text(encoding="utf-8"), str(path), "exec")

encrypted = uploader.protect_token("local-test-token")
assert "local-test-token" not in encrypted
assert uploader.protect_token(encrypted, decrypt=True) == "local-test-token"
for invalid in ["http://img.example.com", "https://user:token@img.example.com", "https://img.example.com/path", "https://img.example.com?token=test"]:
    try:
        uploader.validate_base_url(invalid)
        raise AssertionError("invalid URL accepted")
    except ValueError:
        pass

image = Image.new("RGBA", (1000, 600), (255, 255, 255, 0))
draw = ImageDraw.Draw(image)
draw.rectangle((40, 40, 960, 560), fill=(255, 255, 255, 255))
draw.text((80, 100), "Typora upload integration test", fill=(20, 30, 40, 255))
png = ROOT / "透明截图 测试.png"
image.save(png)
data, extension, mime = uploader.prepare_image(png)
assert len(data) <= png.stat().st_size
converted = Image.open(io.BytesIO(data)).convert("RGBA")
assert converted.size == image.size
assert converted.getchannel("A").tobytes() == image.getchannel("A").tobytes()
for point in [(80, 80), (80, 100), (500, 300)]:
    assert converted.getpixel(point) == image.getpixel(point)

jpeg = ROOT / "照片测试.jpg"
image.convert("RGB").save(jpeg, quality=98)
jpeg_data, jpeg_ext, _ = uploader.prepare_image(jpeg)
assert len(jpeg_data) < jpeg.stat().st_size and jpeg_ext == ".webp"

animation = ROOT / "动图.gif"
frames = [Image.new("RGB", (30, 30), color) for color in ["red", "blue"]]
frames[0].save(animation, save_all=True, append_images=frames[1:], duration=100, loop=0)
assert uploader.prepare_image(animation)[0] == animation.read_bytes()

captured = []

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        message = BytesParser(policy=default).parsebytes(
            ("Content-Type: " + self.headers["Content-Type"] + "\r\n\r\n").encode() + body)
        parts = list(message.iter_parts())
        assert len(parts) == 1
        assert parts[0].get_param("name", header="content-disposition") == "file"
        assert parts[0].get_payload(decode=True) == jpeg_data
        assert self.headers["Authorization"] == "Bearer local-test-token"
        assert "uploadChannel=s3" in self.path
        assert "autoRetry=false" in self.path
        captured.append(self.path)
        if "channelName=fail" in self.path:
            self.send_response(401)
            self.end_headers()
            return
        if "channelName=redirect" in self.path:
            self.send_response(302)
            self.send_header("Location", "https://other.example.com")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        result = {"src": "https://img.example.com/file/test.webp"}
        if "channelName=array" in self.path:
            result = [result]
        self.wfile.write(json.dumps(result).encode())

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
config = {"baseUrl": f"http://127.0.0.1:{server.server_port}", "uploadFolder": "typora"}
try:
    for channel in ["object", "array"]:
        assert uploader.upload_one(jpeg, dict(config, channelName=channel), "local-test-token") == "https://img.example.com/file/test.webp"
    for channel, status in [("fail", 401), ("redirect", 302)]:
        try:
            uploader.upload_one(jpeg, dict(config, channelName=channel), "local-test-token")
            raise AssertionError("error or redirect not rejected")
        except HTTPError as error:
            assert error.code == status
finally:
    server.shutdown()
    server.server_close()

# 模拟两张图中第二张失败：stdout 不能出现可被 Typora 当作成功的部分链接。
old_config, old_upload, old_validate = uploader.CONFIG, uploader.upload_one, uploader.validate_base_url
test_config = ROOT / "mock-config.json"
test_config.write_text(json.dumps({"baseUrl": "https://img.example.com", "tokenDpapi": encrypted}), encoding="utf-8")
uploader.CONFIG = test_config
calls = []
def partial_upload(*args, **kwargs):
    calls.append(args)
    if len(calls) == 2:
        raise ValueError("expected test failure")
    return "https://img.example.com/first.webp"
uploader.upload_one = partial_upload
output = io.StringIO()
try:
    with contextlib.redirect_stdout(output):
        try:
            uploader.main([str(png), str(jpeg)])
        except ValueError:
            pass
    assert output.getvalue() == ""
finally:
    uploader.CONFIG, uploader.upload_one, uploader.validate_base_url = old_config, old_upload, old_validate

print(json.dumps({"result": "passed", "originalPngBytes": png.stat().st_size,
    "uploadedPngBytes": len(data), "pngFormat": extension, "originalJpegBytes": jpeg.stat().st_size,
    "uploadedJpegBytes": len(jpeg_data), "jpegFormat": jpeg_ext,
    "checks": ["DPAPI round trip", "HTTPS validation", "PNG transparency and pixels",
    "JPEG WebP reduction", "animation preservation", "multipart API object and array",
    "HTTP error handling", "credential redirect prevention", "partial failure stdout"]}, ensure_ascii=False, indent=2))
