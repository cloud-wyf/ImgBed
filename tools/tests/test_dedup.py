"""验证去重的请求、失效、并发/回收协调边界，不使用真实凭据或云端文件。"""
import hashlib
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deduplicate import RemoteVerifier, image_key, reuse_or_upload
from local_index import UploadIndex
from recycle import DAY, finish_move, update_absence
import upload

BASE = "https://slanwyf-imgbed.pages.dev"
CONFIG = {"baseUrl": BASE, "channelName": "S3_env", "uploadFolder": "typora"}
URL = BASE + "/file/typora/original.webp"
PAYLOAD = b"same-image-content"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
MIME = "image/webp"


class DedupTests(unittest.TestCase):
    def setUp(self):
        self.index = UploadIndex(":memory:")
        self.addCleanup(self.index.connection.close)

    def run_upload(self, verify, send, config=None, payload=PAYLOAD):
        return reuse_or_upload(payload, MIME, config or CONFIG, self.index, verify, send)

    def test_first_upload_then_identical_content_reuses_url(self):
        verify, send = Mock(return_value=True), Mock(return_value=URL)
        self.assertEqual(self.run_upload(verify, send), (URL, False))
        verify.assert_not_called()
        self.assertEqual(self.run_upload(verify, send), (URL, True))
        send.assert_called_once()
        entry = self.index.lookup(CONFIG, DIGEST)
        self.assertEqual(entry["sha256"], DIGEST)
        self.assertEqual(entry["size"], len(PAYLOAD))

    def test_different_bytes_require_upload(self):
        send = Mock(return_value=URL)
        verify = Mock(return_value=True)
        self.run_upload(verify, send)
        self.run_upload(verify, send, payload=b"changed-image")
        self.assertEqual(send.call_count, 2)
        verify.assert_not_called()

    def test_scopes_isolate_host_channel_and_folder(self):
        send = Mock(return_value=URL)
        self.run_upload(Mock(return_value=True), send)
        for changed in [{"baseUrl": "https://other.example"}, {"channelName": "other"}, {"uploadFolder": "other"}]:
            self.assertIsNone(self.index.lookup(dict(CONFIG, **changed), DIGEST))

    def test_missing_record_uploads_fresh_and_replaces_index(self):
        self.index.remember(CONFIG, DIGEST, URL, "typora/original.webp", len(PAYLOAD), MIME)
        fresh = BASE + "/file/typora/new.webp"
        self.assertEqual(self.run_upload(Mock(return_value=False), Mock(return_value=fresh)), (fresh, False))
        self.assertEqual(self.index.lookup(CONFIG, DIGEST)["url"], fresh)

    def test_transient_failure_preserves_cache_and_never_uploads(self):
        self.index.remember(CONFIG, DIGEST, URL, "typora/original.webp", len(PAYLOAD), MIME)
        send = Mock(return_value=URL)
        with self.assertRaisesRegex(RuntimeError, "temporary"):
            self.run_upload(Mock(side_effect=RuntimeError("temporary")), send)
        send.assert_not_called()
        self.assertIsNotNone(self.index.lookup(CONFIG, DIGEST))

    def test_failed_upload_never_writes_index(self):
        with self.assertRaises(RuntimeError):
            self.run_upload(Mock(), Mock(side_effect=RuntimeError("failed")))
        self.assertIsNone(self.index.lookup(CONFIG, DIGEST))

    def test_recycle_invalidation_removes_all_scopes_only_on_matching_host(self):
        self.index.remember(CONFIG, DIGEST, URL, "typora/original.webp", len(PAYLOAD), MIME)
        another_channel = dict(CONFIG, channelName="another")
        self.index.remember(another_channel, DIGEST, URL, "typora/original.webp", len(PAYLOAD), MIME)
        other_host = dict(CONFIG, baseUrl="https://other.example")
        self.index.remember(other_host, DIGEST, "https://other.example/file/typora/original.webp",
            "typora/original.webp", len(PAYLOAD), MIME)
        self.index.forget_file(BASE, "typora/original.webp")
        self.assertIsNone(self.index.lookup(CONFIG, DIGEST))
        self.assertIsNone(self.index.lookup(another_channel, DIGEST))
        self.assertIsNotNone(self.index.lookup(other_host, DIGEST))

    def test_trash_and_external_urls_cannot_enter_active_cache(self):
        for url in [BASE + "/file/回收站/a.webp", "https://other.example/file/typora/a.webp",
                    BASE + "/file/typora/../a.webp", BASE + "/file/typora/a.webp?secret=value"]:
            self.assertIsNone(image_key(url, CONFIG))

    def test_recent_reuse_resets_absence_even_before_document_saved(self):
        now = 31 * DAY
        state = {"absence": {"typora/original.webp": 0}, "lastSuccessfulScan": now - DAY}
        self.index.remember(CONFIG, DIGEST, URL, "typora/original.webp", len(PAYLOAD), MIME, now=now - 10)
        candidates = update_absence(state, {"typora/original.webp"}, set(), now, 30, 2,
            self.index.last_uses(CONFIG))
        self.assertEqual(candidates, [])
        self.assertEqual(state["absence"]["typora/original.webp"], now - 10)


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.entry = {"url": URL, "file_key": "typora/original.webp", "size": len(PAYLOAD), "mime": MIME}
        self.metadata = {"Channel": "S3", "ChannelName": "S3_env", "S3FileKey": "typora/original.webp"}
        self.bed = Mock()
        self.bed.list_files.return_value = {"typora/original.webp": {"metadata": self.metadata}}
        self.b2 = Mock()
        self.b2.versions.return_value = [{"action": "upload", "contentLength": len(PAYLOAD),
            "contentSha1": "unverified:" + hashlib.sha1(PAYLOAD).hexdigest()}]

    def verifier(self):
        verify = RemoteVerifier(CONFIG)
        verify.bed, verify.b2 = self.bed, self.b2
        return verify

    def test_checks_metadata_and_b2_bytes_signature_without_download(self):
        self.assertTrue(self.verifier()(self.entry, PAYLOAD, MIME))
        self.bed.list_files.assert_called_once_with("typora")
        self.b2.versions.assert_called_once_with("typora/original.webp")

    def test_record_moved_to_trash_is_not_reused(self):
        self.bed.list_files.return_value = {}
        self.assertFalse(self.verifier()(self.entry, PAYLOAD, MIME))
        self.b2.versions.assert_not_called()

    def test_same_path_overwritten_or_hidden_is_not_reused(self):
        for version in [{"action": "hide"}, {"action": "upload", "contentLength": len(PAYLOAD), "contentSha1": "different"}]:
            self.b2.versions.return_value = [version]
            self.assertFalse(self.verifier()(self.entry, PAYLOAD, MIME))

    def test_foreign_channel_blocks_reuse(self):
        self.metadata["ChannelName"] = "another-channel"
        self.assertFalse(self.verifier()(self.entry, PAYLOAD, MIME))
        self.b2.versions.assert_not_called()


class RecycleIntegration(unittest.TestCase):
    def test_successful_recycle_invalidates_index(self):
        from test_recycle import FakeB2, FakeBed
        with UploadIndex(":memory:") as index:
            source = "typora/original.webp"
            index.remember(CONFIG, DIGEST, URL, source, len(PAYLOAD), MIME)
            latest = {"action": "upload", "fileId": "source", "uploadTimestamp": 1,
                "contentLength": len(PAYLOAD), "contentSha1": "abcdef"}
            b2 = FakeB2({source: [latest]})
            operation = {"source": source, "destination": "回收站/a.webp", "latestSource": latest,
                "sourceVersionIds": ["source"], "trashFolder": "回收站"}
            wrapper = Mock()
            wrapper.__enter__ = Mock(return_value=index)
            wrapper.__exit__ = Mock(return_value=False)
            with patch("recycle.UploadIndex", return_value=wrapper):
                finish_move(FakeBed(b2), b2, operation, lambda: None)
            self.assertIsNone(index.lookup(CONFIG, DIGEST))
            self.assertEqual(b2.versions(source), [])


class UploaderIntegration(unittest.TestCase):
    def setUp(self):
        self.index = UploadIndex(":memory:")
        self.addCleanup(self.index.connection.close)
        settings = Mock()
        settings.is_file.return_value = True
        settings.read_text.return_value = json.dumps(dict(CONFIG, tokenDpapi="test-only"))
        for mocked in [patch("upload.CONFIG", settings),
                patch("upload.protect_token", return_value="test-only"),
                patch("upload.local_lock", side_effect=lambda **kwargs: contextlib.nullcontext()),
                patch("upload.UploadIndex", side_effect=lambda: contextlib.nullcontext(self.index)),
                patch("upload.RemoteVerifier", side_effect=lambda config: Mock(return_value=True))]:
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_same_content_in_two_paths_outputs_two_urls_but_sends_once(self):
        output = io.StringIO()
        with patch("upload.prepare_image", return_value=(PAYLOAD, ".webp", MIME)), \
                patch("upload.send_image", return_value=URL) as send, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            upload.main(["first-document-image.png", "second-document-image.png"])
        self.assertEqual(output.getvalue(), URL + "\n" + URL + "\n")
        send.assert_called_once()

    def test_partial_failure_outputs_nothing_and_retry_reuses_success(self):
        other = b"another-image-content"
        other_url = BASE + "/file/typora/another.webp"
        prepare = [(PAYLOAD, ".webp", MIME), (other, ".webp", MIME)]
        output = io.StringIO()
        with patch("upload.prepare_image", side_effect=prepare), \
                patch("upload.send_image", side_effect=[URL, RuntimeError("expected failure")]), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "expected failure"):
                upload.main(["first.png", "second.png"])
        self.assertEqual(output.getvalue(), "")
        self.assertIsNotNone(self.index.lookup(CONFIG, DIGEST))
        self.assertIsNone(self.index.lookup(CONFIG, hashlib.sha256(other).hexdigest()))
        with patch("upload.prepare_image", side_effect=prepare), \
                patch("upload.send_image", return_value=other_url) as send, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            upload.main(["first.png", "second.png"])
        send.assert_called_once()
        self.assertEqual(output.getvalue(), URL + "\n" + other_url + "\n")


if __name__ == "__main__":
    unittest.main()
