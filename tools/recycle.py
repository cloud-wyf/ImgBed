"""每日核对笔记引用；满 30 天未引用的图片移入回收站并永久删除源版本。"""
import argparse
import base64
from datetime import datetime, timezone
import html
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from upload import NoRedirect, protect_token, validate_base_url
from local_index import UploadIndex, local_lock

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "recycle-config.json"
STATE = ROOT / "recycle-state.json"
REPORT = ROOT / "recycle-report.json"
DAY = 86400
URL_PATTERN = re.compile(r"https?://[^\s<>\"'`\[\](){}\\]+", re.IGNORECASE)


def save_json(path, data):
    """同目录原子替换，避免中断后误丢失计时或待完成操作。"""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def json_request(opener, url, headers, body=None):
    request = urllib.request.Request(url, headers=headers,
        data=None if body is None else json.dumps(body).encode("utf-8"))
    try:
        with opener.open(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # 仅保留错误代码，不把服务器响应或认证信息写入日志。
        code = ""
        try:
            code = json.loads(error.read(4096)).get("code", "")
        except (ValueError, AttributeError):
            pass
        raise RuntimeError(f"接口 HTTP {error.code}" + (f" ({code})" if code else "")) from None


class ImageBed:
    def __init__(self, base_url):
        self.base = validate_base_url(base_url)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
        self.headers = {"Content-Type": "application/json", "Accept": "application/json",
            "Origin": self.base, "Referer": self.base + "/dashboard", "User-Agent": "TyporaImgBed/1.0"}
        credentials = json.loads(protect_token(
            (ROOT / "backend-credentials.dpapi").read_text(encoding="ascii"), decrypt=True))
        result = self.request("/api/auth/adminLogin", {
            "username": credentials["username"], "password": credentials["password"]})
        if not result.get("success"):
            raise RuntimeError("图床后台登录失败。")

    def request(self, path, body=None):
        return json_request(self.opener, self.base + path, self.headers, body)

    def list_files(self, folder):
        # 当前接口先读完整索引再分页；一次读清单避免反复扫描同一索引。
        query = urllib.parse.urlencode({"dir": folder, "recursive": "true", "count": -1})
        result = self.request("/api/manage/list?" + query)
        files = result.get("files")
        if not isinstance(files, list) or result.get("totalCount") != len(files):
            raise RuntimeError("图床清单不完整，本次停止核对。")
        names = [file.get("name") for file in files]
        if any(not isinstance(name, str) or not name.startswith(folder + "/") for name in names):
            raise RuntimeError("图床返回了扫描目录外的记录。")
        if len(set(names)) != len(names):
            raise RuntimeError("图床清单存在重复记录。")
        return {file["name"]: file for file in files}

    def move(self, source, destination):
        path = "/api/manage/rename/" + urllib.parse.quote(source, safe="/")
        result = self.request(path, {"newFileId": destination})
        if not result.get("success") or result.get("newFileId") != destination:
            raise RuntimeError("图床移入回收站失败。")


class Backblaze:
    def __init__(self, expected_bucket):
        credentials = json.loads(protect_token(
            (ROOT / "b2-credentials.dpapi").read_text(encoding="ascii"), decrypt=True))
        basic = base64.b64encode((credentials["keyId"] + ":" + credentials["applicationKey"]).encode()).decode()
        self.opener = urllib.request.build_opener(NoRedirect())
        authorization = json_request(self.opener,
            "https://api.backblazeb2.com/b2api/v4/b2_authorize_account",
            {"Authorization": "Basic " + basic, "User-Agent": "TyporaImgBed/1.0"})
        storage = authorization["apiInfo"]["storageApi"]
        allowed = storage["allowed"]
        buckets = allowed.get("buckets", [])
        if len(buckets) != 1 or buckets[0].get("name") != expected_bucket:
            raise RuntimeError("B2 密钥未限定于配置的图床桶。")
        if not {"readFiles", "listFiles", "deleteFiles"}.issubset(allowed.get("capabilities", [])):
            raise RuntimeError("B2 密钥缺少查询或永久删除版本的权限。")
        self.bucket_id = buckets[0]["id"]
        self.api = validate_base_url(storage["apiUrl"])
        if not urllib.parse.urlsplit(self.api).hostname.endswith(".backblazeb2.com"):
            raise RuntimeError("B2 返回了非预期的 API 域名。")
        self.headers = {"Authorization": authorization["authorizationToken"],
            "Content-Type": "application/json", "User-Agent": "TyporaImgBed/1.0"}

    def request(self, operation, body):
        return json_request(self.opener, self.api + "/b2api/v4/" + operation, self.headers, body)

    def versions(self, key):
        files, cursor = [], {}
        seen = set()
        while True:
            result = self.request("b2_list_file_versions", {
                "bucketId": self.bucket_id, "prefix": key, "maxFileCount": 1000, **cursor})
            files.extend(file for file in result["files"] if file["fileName"] == key)
            next_name, next_id = result.get("nextFileName"), result.get("nextFileId")
            if not next_name or next_name != key:
                break
            if (next_name, next_id) in seen:
                raise RuntimeError("B2 版本分页重复，本次停止。")
            seen.add((next_name, next_id))
            cursor = {"startFileName": next_name, "startFileId": next_id}
        return files

    def delete_version(self, key, version_id):
        self.request("b2_delete_file_version", {"fileName": key, "fileId": version_id})


def extract_references(body, base_url):
    host = urllib.parse.urlsplit(base_url).netloc.lower()
    references = set()
    for raw in URL_PATTERN.findall(html.unescape(body)):
        # Markdown/HTML 的结束分隔符不是生成的图床文件名的一部分。
        raw = raw.rstrip(".,;)]}\\")
        url = urllib.parse.urlsplit(raw)
        if url.netloc.lower() == host and url.path.startswith("/file/"):
            references.add(urllib.parse.unquote(url.path[len("/file/"):]))
    return references


def scan_notes(roots, base_url):
    references = set()
    documents = 0
    for root_text in roots:
        root = Path(root_text)
        if not root.is_dir() or root.is_symlink() or root.is_junction():
            raise RuntimeError("笔记根目录不可访问或为链接，本次停止。")
        errors = []
        for directory, folders, files in os.walk(root, onerror=errors.append):
            for folder in folders:
                child = Path(directory) / folder
                if child.is_symlink() or child.is_junction():
                    raise RuntimeError("笔记目录含链接目录，请先明确完整扫描范围。")
            for filename in files:
                if Path(filename).suffix.lower() not in {".md", ".markdown"}:
                    continue
                path = Path(directory) / filename
                if path.is_symlink():
                    raise RuntimeError("笔记文件为符号链接，本次停止。")
                before = path.stat()
                raw = path.read_bytes()
                if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                    body = raw.decode("utf-16")
                else:
                    try:
                        body = raw.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        body = raw.decode("gb18030")
                after = path.stat()
                if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                    raise RuntimeError("扫描时文档发生变化，本次停止。")
                references.update(extract_references(body, base_url))
                documents += 1
        if errors:
            raise RuntimeError("部分笔记目录无法读取，本次停止。")
    if documents == 0:
        raise RuntimeError("未读到任何笔记，本次停止。")
    return references, documents


def update_absence(state, keys, references, now, days, max_gap_days, last_uses=None):
    previous = state.get("lastSuccessfulScan")
    if previous is not None and (now < previous or now - previous > max_gap_days * DAY):
        state["absence"] = {}
    absence = state.setdefault("absence", {})
    for key in list(absence):
        if key not in keys or key in references:
            del absence[key]
    candidates = []
    for key in sorted(keys):
        if key in references:
            continue
        first = absence.setdefault(key, now)
        # 刚上传或复用的链接可能还未保存到 Markdown，重新开始无引用等待。
        first = max(first, min((last_uses or {}).get(key, first), now))
        absence[key] = first
        if now - first >= days * DAY:
            candidates.append(key)
    state["lastSuccessfulScan"] = now
    return candidates


def normalized_sha1(version):
    return version.get("contentSha1", "").removeprefix("unverified:")


def verify_copy(source, destination):
    if (destination.get("action") != "upload"
            or source.get("contentLength") != destination.get("contentLength")
            or not normalized_sha1(source)
            or normalized_sha1(source) != normalized_sha1(destination)):
        raise RuntimeError("回收站副本的大小或校验值不一致，保留源文件。")


def finish_move(bed, b2, operation, checkpoint):
    source, destination = operation["source"], operation["destination"]
    # 网络中断时允许核对已完成的复制；每个回收操作使用唯一目标名。
    destination_versions = b2.versions(destination)
    if not destination_versions:
        source_versions = b2.versions(source)
        if not source_versions or source_versions[0]["fileId"] != operation["latestSource"]["fileId"]:
            raise RuntimeError("源文件版本发生变化，本次停止复制。")
        bed.move(source, destination)
        destination_versions = b2.versions(destination)
    if not destination_versions:
        raise RuntimeError("回收站未找到副本，源版本不做永久删除。")
    verify_copy(operation["latestSource"], destination_versions[0])
    # 原元数据已由图床 rename 接口迁移，确认管理记录也已落盘。
    destination_record = bed.list_files(operation["trashFolder"]).get(destination)
    if not destination_record or destination_record.get("metadata", {}).get("S3FileKey") != destination:
        raise RuntimeError("回收站管理记录未完成，保留源版本并等待重试。")
    operation["copied"] = True
    checkpoint()
    current = b2.versions(source)
    original_ids = set(operation["sourceVersionIds"])
    # 回收后若同名路径出现了新上传版本，不允许误删新数据。
    if any(file["action"] not in {"upload", "hide"} or
           (file["action"] == "upload" and file["fileId"] not in original_ids) for file in current):
        raise RuntimeError("源路径出现新版本，停止永久删除，请人工核对。")
    # 先删数据版本，最后删标记，途中保持原路径隐藏。
    ordered = sorted(current, key=lambda file: (file["action"] == "hide", file["uploadTimestamp"]))
    for version in ordered:
        b2.delete_version(source, version["fileId"])
    if b2.versions(source):
        raise RuntimeError("源路径仍有版本，等待下次核对。")
    with UploadIndex() as index:
        index.forget_file(bed.base, source)
    operation["completedAt"] = time.time()
    checkpoint()


def recycle_one(bed, b2, source, trash_folder, state, checkpoint):
    versions = b2.versions(source)
    if not versions or versions[0]["action"] != "upload":
        raise RuntimeError("源图片不存在或已隐藏，本次不回收。")
    if any(version["action"] not in {"upload", "hide"} for version in versions):
        raise RuntimeError("源图片存在未完成上传，本次不回收。")
    operation = {"source": source,
        "destination": trash_folder + "/" + uuid.uuid4().hex + "_" + source.rsplit("/", 1)[-1],
        "trashFolder": trash_folder, "latestSource": versions[0],
        "sourceVersionIds": [version["fileId"] for version in versions], "startedAt": time.time()}
    state.setdefault("pending", {})[source] = operation
    checkpoint()
    finish_move(bed, b2, operation, checkpoint)
    state["pending"].pop(source)
    state.setdefault("recycled", []).append(operation)
    state["absence"].pop(source, None)
    checkpoint()
    return operation


def single_instance():
    return local_lock()


def run(apply=False):
    config = json.loads(SETTINGS.read_text(encoding="utf-8"))
    uploader = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    base = validate_base_url(uploader["baseUrl"])
    active = config["activeFolder"]
    trash = config["trashFolder"]
    if active != "typora" or trash != "回收站" or config["unreferencedDays"] != 30:
        raise ValueError("当前回收策略仅允许 typora → 回收站，连续 30 天未引用。")
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {
        "schemaVersion": 1, "absence": {}, "pending": {}, "recycled": []}
    identity = {"roots": config["noteRoots"], "baseUrl": base, "active": active, "trash": trash}
    if state.get("identity", identity) != identity:
        raise RuntimeError("扫描范围或图床发生变化，请人工确认后重新初始化计时。")
    state["identity"] = identity
    references, documents = scan_notes(config["noteRoots"], base)
    bed = ImageBed(base)
    files = bed.list_files(active)
    eligible = {name for name, file in files.items()
        if file.get("metadata", {}).get("Channel") == "S3"
        and file["metadata"].get("ChannelName") == uploader["channelName"]
        and file["metadata"].get("S3FileKey") == name
        and str(file["metadata"].get("FileType", "")).startswith("image/")}
    with UploadIndex() as index:
        last_uses = index.last_uses(uploader)
    candidates = update_absence(state, eligible, references, time.time(),
        config["unreferencedDays"], config["maxScanGapDays"], last_uses)
    report = {"time": datetime.now(timezone.utc).isoformat(), "mode": "apply" if apply else "preview",
        "documentsScanned": documents, "imagesInTypora": len(eligible),
        "referencedImages": len(eligible & references), "trackingUnreferenced": len(state["absence"]),
        "readyToRecycle": candidates, "recycled": [], "errors": []}
    if apply:
        checkpoint = lambda: save_json(STATE, state)
        checkpoint()
        if state["pending"] or candidates:
            b2 = Backblaze(config["bucketName"])
            for source, operation in list(state["pending"].items()):
                latest_refs, _ = scan_notes(config["noteRoots"], base)
                if source in latest_refs:
                    report["errors"].append({"source": source, "error": "中断的回收操作重新出现引用，需人工核对。"})
                    continue
                try:
                    finish_move(bed, b2, operation, checkpoint)
                    state["pending"].pop(source)
                    state["recycled"].append(operation)
                    state["absence"].pop(source, None)
                    checkpoint()
                    report["recycled"].append(source)
                except (RuntimeError, OSError, ValueError) as error:
                    report["errors"].append({"source": source, "error": str(error)})
            completed_or_pending = set(report["recycled"]) | set(state["pending"])
            for source in candidates:
                if len(report["recycled"]) >= config["maxMovesPerRun"]:
                    break
                if source in completed_or_pending:
                    continue
                try:
                    # 执行破坏性操作前重扫，刚保存的引用不会被旧快照忽略。
                    latest_refs, _ = scan_notes(config["noteRoots"], base)
                    if source in latest_refs:
                        state["absence"].pop(source, None)
                        checkpoint()
                        continue
                    recycle_one(bed, b2, source, trash, state, checkpoint)
                    report["recycled"].append(source)
                except (RuntimeError, OSError, ValueError) as error:
                    report["errors"].append({"source": source, "error": str(error)})
                    break
        save_json(REPORT, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="保存核对状态并执行已到期的回收")
    args = parser.parse_args()
    try:
        with single_instance():
            report = run(args.apply)
        output = json.dumps(report, ensure_ascii=False, indent=2)
        if sys.stdout:
            print(output)
        return 1 if report["errors"] else 0
    except Exception as error:
        # 输出本地诊断，不保存调用堆栈、认证头或接口响应。
        message = str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
        failure = {"time": datetime.now(timezone.utc).isoformat(), "mode": "error", "error": message}
        save_json(REPORT, failure)
        if sys.stderr:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr:
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
