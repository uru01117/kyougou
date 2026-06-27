#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
競合ウォッチ用 MNP/新規契約キャンペーン自動取得スクリプト

データソース: 価格.com (kakaku.com)
  - キャリア公式サイト(ahamo.com, au.com など)は robots.txt で
    自動アクセスを禁止しているため対象にしていません。
  - 価格.com の格安SIM/キャンペーン比較ページは meta robots が
    index,follow になっており、一般公開情報として集計・引用しています。

実行すると campaigns.json を生成します。
GitHub Actions から毎日実行することを想定しています。
"""

import json
import re
import sys
import time
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "CompetitorWatchBot/1.0 (+personal small-business use; contact via GitHub repo owner)"
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = 15

# 監視対象キャリア: kakaku.com の格安SIMキャンペーンページ
# (mvno/<id>/campaign/ の <id> は価格.com 内のキャリアID)
TARGETS = [
    {"carrier": "ahamo",         "url": "https://kakaku.com/mobile_data/sim/mvno/11/campaign/"},
    {"carrier": "楽天モバイル",   "url": "https://kakaku.com/mobile_data/sim/mvno/37/campaign/"},
    {"carrier": "ワイモバイル",   "url": "https://kakaku.com/mobile_data/sim/mvno/45/campaign/"},
    {"carrier": "UQ mobile",     "url": "https://kakaku.com/mobile_data/sim/mvno/49/campaign/"},
    {"carrier": "povo2.0",       "url": "https://kakaku.com/mobile_data/sim/mvno/13/campaign/"},
]

# 金額/ポイントの抜き出し用パターン (例: 20,000ポイント / 15,000円相当 / 40%還元)
AMOUNT_PATTERN = re.compile(
    r"(\d{1,3}(?:,\d{3})*\s*(?:円相当|円分|円|ポイント|pt|%還元))"
)

_robots_cache = {}


def is_allowed(url: str) -> bool:
    """robots.txt を確認し、このURLへの自動アクセスが許可されているか判定する。"""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(base + "/robots.txt")
        try:
            rp.read()
        except Exception:
            # robots.txt が読めない場合は安全側に倒して「不許可」とする
            _robots_cache[base] = None
            return False
        _robots_cache[base] = rp
    rp = _robots_cache[base]
    if rp is None:
        return False
    return rp.can_fetch(USER_AGENT, url)


def fetch_campaign(target: dict) -> dict:
    carrier = target["carrier"]
    url = target["url"]

    if not is_allowed(url):
        return {
            "carrier": carrier,
            "amount": None,
            "note": "robots.txtにより自動取得が許可されていないため取得をスキップしました",
            "source_url": url,
            "status": "blocked",
        }

    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
    except Exception as e:
        return {
            "carrier": carrier,
            "amount": None,
            "note": f"取得失敗: {e}",
            "source_url": url,
            "status": "error",
        }

    soup = BeautifulSoup(res.content, "html.parser")

    # ページ本文からキャンペーンの見出し相当のテキストを集める
    # (価格.com のキャンペーンページは見出し的に ####や太字テキストでタイトルを出している)
    text_blocks = []
    for tag in soup.find_all(["h2", "h3", "h4", "strong", "td", "p"]):
        t = tag.get_text(strip=True)
        if t and 2 < len(t) < 200:
            text_blocks.append(t)

    full_text = "\n".join(text_blocks)

    amounts = AMOUNT_PATTERN.findall(full_text)
    # MNP/乗り換え関連の見出しを優先的に拾う
    headline = ""
    for block in text_blocks:
        if ("MNP" in block or "乗り換え" in block or "ポイント" in block) and AMOUNT_PATTERN.search(block):
            headline = block
            break
    if not headline and text_blocks:
        # 見つからなければ金額を含む最初の行
        for block in text_blocks:
            if AMOUNT_PATTERN.search(block):
                headline = block
                break

    best_amount = amounts[0] if amounts else None

    return {
        "carrier": carrier,
        "amount": best_amount,
        "note": headline or "現在ページ内に金額表記の見出しが見つかりませんでした(要目視確認)",
        "source_url": url,
        "status": "ok" if best_amount else "no_amount_found",
    }


def main():
    results = []
    for target in TARGETS:
        item = fetch_campaign(target)
        results.append(item)
        print(f"[{item['status']}] {item['carrier']}: {item.get('amount')} - {item.get('note')}", file=sys.stderr)
        time.sleep(2)  # サーバーに負荷をかけないよう間隔を空ける

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "kakaku.com (価格.com) 格安SIM/キャンペーン比較ページ",
        "items": results,
    }

    with open("campaigns.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("campaigns.json を出力しました。", file=sys.stderr)


if __name__ == "__main__":
    main()
