"""本机内容索引与上传/回收互斥锁，不保存凭据或图片内容。"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "upload-index.sqlite3"


@contextmanager
def local_lock(wait_seconds=0):
    """上传与回收共用锁；进程退出时 Windows 自动释放。"""
    import msvcrt
    with (ROOT / "recycle.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + wait_seconds
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError("上传或回收任务正在运行，请稍后重试。") from None
                time.sleep(0.2)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def target_scope(config):
    return json.dumps([config["baseUrl"].rstrip("/"), config.get("channelName", ""),
        str(config.get("uploadFolder", "typora")).strip("/")], separators=(",", ":"))


class UploadIndex:
    def __init__(self, path=None):
        self.connection = sqlite3.connect(path or DATABASE)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("""CREATE TABLE IF NOT EXISTS uploads (
                scope TEXT NOT NULL, sha256 TEXT NOT NULL, url TEXT NOT NULL,
                file_key TEXT NOT NULL, size INTEGER NOT NULL, mime TEXT NOT NULL,
                used_at REAL NOT NULL, PRIMARY KEY (scope, sha256))""")
            self.connection.commit()
        except Exception:
            self.connection.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def lookup(self, config, digest):
        row = self.connection.execute("SELECT * FROM uploads WHERE scope=? AND sha256=?",
            (target_scope(config), digest)).fetchone()
        return dict(row) if row else None

    def remember(self, config, digest, url, key, size, mime, now=None):
        self.connection.execute("""INSERT OR REPLACE INTO uploads
            (scope, sha256, url, file_key, size, mime, used_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (target_scope(config), digest, url, key, size, mime, time.time() if now is None else now))
        self.connection.commit()

    def forget(self, config, digest):
        self.connection.execute("DELETE FROM uploads WHERE scope=? AND sha256=?",
            (target_scope(config), digest))
        self.connection.commit()

    def forget_file(self, base_url, key):
        # 同一图床的所有渠道/目录索引均移除该文件，其他图床保留。
        rows = self.connection.execute("SELECT scope, sha256 FROM uploads WHERE file_key=?", (key,)).fetchall()
        for row in rows:
            if json.loads(row["scope"])[0] == base_url.rstrip("/"):
                self.connection.execute("DELETE FROM uploads WHERE scope=? AND sha256=?",
                    (row["scope"], row["sha256"]))
        self.connection.commit()

    def last_uses(self, config):
        rows = self.connection.execute("SELECT file_key, MAX(used_at) AS used_at FROM uploads WHERE scope=? GROUP BY file_key",
            (target_scope(config),)).fetchall()
        return {row["file_key"]: row["used_at"] for row in rows}
