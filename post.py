#!/usr/bin/env python3
"""images/ から1枚ランダムに選び Instagram に投稿 → 成功したら posted/ へ移動。

env: IG_TOKEN, IG_USER_ID (必須) / NEW_TOKEN_FILE (任意: 延長したトークンの書き出し先)
     GITHUB_REPOSITORY, GITHUB_SHA (Actions が自動で設定)
usage: python post.py [--dry-run]
"""
import json
import os
import random
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://graph.instagram.com/" + os.environ.get("IG_API_VERSION", "v23.0")
ROOT = Path(__file__).parent
IMAGES, POSTED = ROOT / "images", ROOT / "posted"


HINT = ("\n=> token/app is blocked or invalid: check the Meta app dashboard (app status, "
        "notifications), regenerate the token, update the IG_TOKEN secret, then re-run via workflow_dispatch")


def call(method, path, **params):
    # トークンを含む URL / params は絶対に出力しない
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    req = urllib.request.Request(url + "?" + data.decode() if method == "GET" else url,
                                 data=None if method == "GET" else data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        hint = HINT if '"code":190' in body or '"code":200' in body else ""
        sys.exit(f"API error {e.code} on {path}: {body}{hint}")


def refresh_token(token):
    """60日失効を毎日リセット。失敗しても投稿は続行 (前回から24h未満だと拒否される)。"""
    out = os.environ.get("NEW_TOKEN_FILE")
    if not out:
        return
    try:
        url = "https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
            {"grant_type": "ig_refresh_token", "access_token": token})
        with urllib.request.urlopen(url, timeout=60) as r:
            Path(out).write_text(json.load(r)["access_token"])
        print("token refreshed")
    except urllib.error.HTTPError as e:  # 本文にトークンは含まれない
        print(f"warning: token refresh failed: {e.code} {e.read().decode(errors='replace')}")
    except Exception as e:  # noqa: BLE001
        print(f"warning: token refresh skipped ({type(e).__name__})")


def main():
    dry = "--dry-run" in sys.argv
    pool = sorted(p for p in IMAGES.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))
    if not pool:
        print("images/ is empty - nothing to post")
        return
    img = random.choice(pool)
    caption = (ROOT / "caption.txt").read_text(encoding="utf-8").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "owner/repo")
    sha = os.environ.get("GITHUB_SHA", "HEAD")
    url = f"https://raw.githubusercontent.com/{repo}/{sha}/images/{urllib.parse.quote(img.name)}"
    print(f"picked: {img.name}\nurl: {url}")
    if dry:
        return

    token, uid = os.environ["IG_TOKEN"], os.environ["IG_USER_ID"]
    refresh_token(token)

    cid = call("POST", f"{uid}/media", image_url=url, caption=caption, access_token=token)["id"]
    for _ in range(30):  # 最大 ~150秒
        st = call("GET", cid, fields="status_code", access_token=token)["status_code"]
        if st == "FINISHED":
            break
        if st in ("ERROR", "EXPIRED"):
            sys.exit(f"container status: {st}")
        time.sleep(5)
    else:
        sys.exit("container not ready in time")

    call("POST", f"{uid}/media_publish", creation_id=cid, access_token=token)
    POSTED.mkdir(exist_ok=True)
    shutil.move(str(img), POSTED / img.name)
    print(f"posted and moved: {img.name}")


if __name__ == "__main__":
    main()
