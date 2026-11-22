"""核对真实风险边界：引用识别、30 天计时、复制校验和版本永久清理。"""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recycle import DAY, extract_references, update_absence, finish_move
from local_index import UploadIndex

BASE = "https://slanwyf-imgbed.pages.dev"


class References(unittest.TestCase):
    def test_markdown_html_and_encoded_paths(self):
        body = f'''![图]({BASE}/file/typora/a.webp)\n<img src="{BASE}/file/typora/b.png?x=1&amp;y=2">\n[x]({BASE}/file/typora/%E4%B8%AD%E6%96%87.webp)'''
        self.assertEqual(extract_references(body, BASE), {
            "typora/a.webp", "typora/b.png", "typora/中文.webp"})

    def test_other_hosts_never_count(self):
        self.assertEqual(extract_references("https://example.com/file/typora/a.webp", BASE), set())

    def test_markdown_followed_by_chinese_without_space(self):
        self.assertEqual(extract_references(f"![图]({BASE}/file/typora/a.webp)这是说明", BASE), {"typora/a.webp"})

    def test_reference_reappearance_resets_30_day_clock(self):
        state = {"absence": {"a": 0}, "lastSuccessfulScan": 29 * DAY}
        self.assertEqual(update_absence(state, {"a"}, set(), 30 * DAY - 1, 30, 2), [])
        self.assertEqual(update_absence(state, {"a"}, set(), 30 * DAY, 30, 2), ["a"])
        update_absence(state, {"a"}, {"a"}, 30 * DAY + 1, 30, 2)
        self.assertEqual(state["absence"], {})
        update_absence(state, {"a"}, set(), 31 * DAY, 30, 2)
        self.assertEqual(state["absence"]["a"], 31 * DAY)

    def test_long_gap_cannot_count_as_continuously_unreferenced(self):
        state = {"absence": {"a": 0}, "lastSuccessfulScan": DAY}
        self.assertEqual(update_absence(state, {"a"}, set(), 31 * DAY, 30, 2), [])
        self.assertEqual(state["absence"]["a"], 31 * DAY)


class FakeB2:
    def __init__(self, values):
        self.values = copy.deepcopy(values)
        self.deleted = []

    def versions(self, key):
        return copy.deepcopy(self.values.get(key, []))

    def delete_version(self, key, version_id):
        self.deleted.append(version_id)
        self.values[key] = [v for v in self.values[key] if v["fileId"] != version_id]


class FakeBed:
    base = BASE
    def __init__(self, b2, bad_copy=False):
        self.b2, self.bad_copy = b2, bad_copy
        self.moves = 0
        self.destination = None

    def move(self, source, destination):
        self.moves += 1
        self.destination = destination
        copied = copy.deepcopy(self.b2.values[source][0])
        copied.update(fileName=destination, fileId="copy")
        if self.bad_copy:
            copied["contentLength"] += 1
        self.b2.values[destination] = [copied]
        self.b2.values[source].insert(0, {"action": "hide", "fileId": "marker", "uploadTimestamp": 3})

    def list_files(self, folder):
        return {key: {"metadata": {"S3FileKey": key}} for key in self.b2.values if key.startswith(folder + "/")}


class PermanentDeletion(unittest.TestCase):
    def setUp(self):
        self.index_patch = patch("recycle.UploadIndex", lambda: UploadIndex(":memory:"))
        self.index_patch.start()
        self.addCleanup(self.index_patch.stop)
        self.source, self.destination = "typora/a.webp", "回收站/id_a.webp"
        self.latest = {"action": "upload", "fileName": self.source, "fileId": "latest",
            "contentLength": 100, "contentSha1": "unverified:abcdef", "uploadTimestamp": 2}
        older = {**self.latest, "fileId": "older", "uploadTimestamp": 1}
        self.b2 = FakeB2({self.source: [self.latest, older]})
        self.operation = {"source": self.source, "destination": self.destination,
            "latestSource": self.latest, "sourceVersionIds": ["latest", "older"], "trashFolder": "回收站"}

    def test_copy_then_remove_all_source_versions_and_marker(self):
        bed = FakeBed(self.b2)
        finish_move(bed, self.b2, self.operation, lambda: None)
        self.assertEqual(self.b2.versions(self.source), [])
        self.assertEqual(self.b2.deleted, ["older", "latest", "marker"])
        self.assertEqual(self.b2.versions(self.destination)[0]["contentLength"], 100)

    def test_invalid_copy_never_permanently_deletes_source(self):
        with self.assertRaisesRegex(RuntimeError, "校验值"):
            finish_move(FakeBed(self.b2, bad_copy=True), self.b2, self.operation, lambda: None)
        self.assertEqual(self.b2.deleted, [])

    def test_retry_does_not_copy_again(self):
        bed = FakeBed(self.b2)
        bed.move(self.source, self.destination)
        finish_move(bed, self.b2, self.operation, lambda: None)
        self.assertEqual(bed.moves, 1)

    def test_new_source_version_blocks_permanent_deletion(self):
        bed = FakeBed(self.b2)
        bed.move(self.source, self.destination)
        self.b2.values[self.source].insert(0, {**self.latest, "fileId": "new-upload"})
        with self.assertRaisesRegex(RuntimeError, "新版本"):
            finish_move(bed, self.b2, self.operation, lambda: None)
        self.assertEqual(self.b2.deleted, [])


if __name__ == "__main__":
    unittest.main()
