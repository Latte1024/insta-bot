"""post.py のテスト (標準ライブラリのみ・ネットワーク不要)。 usage: python -m unittest -v"""
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import post

BLOCKED = '{"error":{"message":"API access blocked.","type":"OAuthException","code":200}}'


def http_error(code, body):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(body.encode()))


class PostTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.images, self.posted = tmp / "images", tmp / "posted"
        self.images.mkdir()
        (self.images / "a.jpg").write_bytes(b"x")
        (tmp / "caption.txt").write_text("cap", encoding="utf-8")
        env = {"IG_TOKEN": "SECRET", "IG_USER_ID": "1"}
        for p in (mock.patch.object(post, "IMAGES", self.images), mock.patch.object(post, "POSTED", self.posted),
                  mock.patch.object(post, "ROOT", tmp), mock.patch.dict(os.environ, env),
                  mock.patch.object(post.time, "sleep"), mock.patch.object(post.sys, "argv", ["post.py"])):
            p.start()
            self.addCleanup(p.stop)

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            post.main()
        return out.getvalue()

    def test_success_moves_image(self):
        replies = [{"id": "c1"}, {"status_code": "FINISHED"}, {"id": "m1"}]
        with mock.patch.object(post, "call", side_effect=replies) as c:
            self.run_main()
        self.assertEqual(c.call_args_list[-1].args[1], "1/media_publish")
        self.assertTrue((self.posted / "a.jpg").exists() and not (self.images / "a.jpg").exists())

    def test_blocked_api_exits_with_hint_and_keeps_image(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(400, BLOCKED)):
            with self.assertRaises(SystemExit) as cm:
                self.run_main()
        msg = str(cm.exception)
        self.assertIn("API access blocked", msg)
        self.assertIn("regenerate the token", msg)  # 次に何をすべきかが出る
        self.assertNotIn("SECRET", msg)
        self.assertTrue((self.images / "a.jpg").exists())  # 失敗時は移動しない

    def test_container_error_keeps_image(self):
        with mock.patch.object(post, "call", side_effect=[{"id": "c1"}, {"status_code": "ERROR"}]):
            with self.assertRaises(SystemExit):
                self.run_main()
        self.assertTrue((self.images / "a.jpg").exists())

    def test_refresh_failure_is_logged_not_fatal(self):
        out_file = str(self.images.parent / "new_token")
        with mock.patch.dict(os.environ, {"NEW_TOKEN_FILE": out_file}), \
                mock.patch("urllib.request.urlopen", side_effect=http_error(400, BLOCKED)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                post.refresh_token("SECRET")
        self.assertIn("API access blocked", buf.getvalue())
        self.assertNotIn("SECRET", buf.getvalue())
        self.assertFalse(Path(out_file).exists())

    def test_refresh_success_writes_file(self):
        out_file = self.images.parent / "new_token"
        resp = mock.MagicMock()
        resp.__enter__.return_value = io.BytesIO(json.dumps({"access_token": "NEW"}).encode())
        with mock.patch.dict(os.environ, {"NEW_TOKEN_FILE": str(out_file)}), \
                mock.patch("urllib.request.urlopen", return_value=resp), contextlib.redirect_stdout(io.StringIO()):
            post.refresh_token("SECRET")
        self.assertEqual(out_file.read_text(), "NEW")

    def test_dry_run_posts_nothing(self):
        with mock.patch.object(post.sys, "argv", ["post.py", "--dry-run"]), \
                mock.patch.object(post, "call") as c:
            self.run_main()
        c.assert_not_called()
        self.assertTrue((self.images / "a.jpg").exists())

    def test_empty_images_is_noop(self):
        (self.images / "a.jpg").unlink()
        self.assertIn("empty", self.run_main())


if __name__ == "__main__":
    unittest.main()
