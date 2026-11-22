"""对命中本地 SHA-256 索引的图片核对云端元数据，复用有效链接。"""
import hashlib
import json
import time
import urllib.parse

from local_index import ROOT


def image_key(url, config):
    parsed = urllib.parse.urlsplit(url)
    base = urllib.parse.urlsplit(config["baseUrl"])
    folder = str(config.get("uploadFolder", "typora")).strip("/")
    if (parsed.scheme != "https" or parsed.netloc.lower() != base.netloc.lower()
            or parsed.query or parsed.fragment or not parsed.path.startswith("/file/")):
        return None
    key = urllib.parse.unquote(parsed.path[len("/file/"):])
    if not folder or not key.startswith(folder + "/") or any(part in {"", ".", ".."} for part in key.split("/")):
        return None
    return key


class RemoteVerifier:
    """只在缓存命中时登录；不读取图片数据，暂时故障不触发重复上传。"""
    def __init__(self, config):
        self.config = config
        self.bed = None
        self.b2 = None

    def __call__(self, entry, payload, mime):
        key = image_key(entry["url"], self.config)
        if key != entry["file_key"] or entry["size"] != len(payload) or entry["mime"] != mime:
            return False
        # 延迟导入，上传模块与回收模块共享已有认证和元数据查询实现。
        from recycle import ImageBed, Backblaze, normalized_sha1
        if self.bed is None:
            self.bed = ImageBed(self.config["baseUrl"])
        folder = key.rsplit("/", 1)[0]
        record = self.bed.list_files(folder).get(key)
        if not record:
            return False
        metadata = record.get("metadata", {})
        if (metadata.get("Channel") != "S3"
                or metadata.get("ChannelName") != self.config.get("channelName")
                or metadata.get("S3FileKey") != key
                or metadata.get("ListType") == "Block"
                or (metadata.get("ExpiresAt") is not None
                    and metadata["ExpiresAt"] <= time.time() * 1000)):
            return False
        if self.b2 is None:
            settings = json.loads((ROOT / "recycle-config.json").read_text(encoding="utf-8"))
            self.b2 = Backblaze(settings["bucketName"])
        versions = self.b2.versions(key)
        if not versions or versions[0]["action"] != "upload":
            return False
        current = versions[0]
        return (current["contentLength"] == len(payload)
            and normalized_sha1(current) == hashlib.sha1(payload).hexdigest())


def reuse_or_upload(payload, mime, config, index, verify, upload):
    digest = hashlib.sha256(payload).hexdigest()
    entry = index.lookup(config, digest)
    if entry:
        if image_key(entry["url"], config) == entry["file_key"] and verify(entry, payload, mime):
            index.remember(config, digest, entry["url"], entry["file_key"], len(payload), mime)
            return entry["url"], True
        index.forget(config, digest)
    url = upload()
    key = image_key(url, config)
    if key:
        index.remember(config, digest, url, key, len(payload), mime)
    return url, False
