#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Googleアラート(RSS)を取得して、高槻市・茨木市・枚方市の
スマホ新規契約・MNP関連の話題を1つのJSONにまとめるスクリプト。

GitHub Actions から毎日実行することを想定しています。
出力: alerts.json
"""

import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET

import requests

HEADERS = {"User-Agent": "CompetitorWatchBot/1.0 (+personal small-business use)"}
TIMEOUT = 15

ALERTS = [
    {"city": "高槻市", "url": "https://www.google.com/alerts/feeds/02490063615176814970/14492141171966380678"},
    {"city": "茨木市", "url": "https://www.google.com/alerts/feeds/02490063615176814970/9242898230686110022"},
    {"city": "枚方市", "url": "https://www.google.com/alerts/feeds/02490063615176814970/14492141171966380909"},
]

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def clean_html(text: str) -> str:
    """Googleアラートのtitleにはハイライト用の<b>タグなどが入っているので除去する。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def extract_real_url(google_url: str) -> str:
    """Googleアラートのリンクは google.com/url?...&url=実際のURL の形式が多いので展開する。"""
    try:
        parsed = urlparse(google_url)
        qs = parse_qs(parsed.query)
        if "url" in qs and qs["url"]:
            return qs["url"][0]
    except Exception:
        pass
    return google_url


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def fetch_alert(alert: dict) -> list:
    city = alert["city"]
    url = alert["url"]
    items = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
    except Exception as e:
        print(f"[error] {city}: {e}", file=sys.stderr)
        return items

    try:
        root = ET.fromstring(res.content)
    except Exception as e:
        print(f"[parse-error] {city}: {e}", file=sys.stderr)
        return items

    for entry in root.findall("atom:entry", ATOM_NS):
        title_el = entry.find("atom:title", ATOM_NS)
        link_el = entry.find("atom:link", ATOM_NS)
        published_el = entry.find("atom:published", ATOM_NS)

        title = clean_html(title_el.text if title_el is not None else "")
        raw_link = link_el.get("href") if link_el is not None else ""
        real_link = extract_real_url(raw_link)
        published = published_el.text if published_el is not None else ""

        if not title:
            continue

        items.append({
            "city": city,
            "title": title,
            "link": real_link,
            "source": domain_of(real_link),
            "published": published,
        })

    return items


def main():
    all_items = []
    for alert in ALERTS:
        found = fetch_alert(alert)
        print(f"[ok] {alert['city']}: {len(found)}件", file=sys.stderr)
        all_items.extend(found)

    # 新しい順に並び替え(published が ISO8601 なので文字列比較でも概ね並ぶ)
    all_items.sort(key=lambda x: x.get("published") or "", reverse=True)

    # 件数が多くなりすぎないよう全体で上限を設ける
    all_items = all_items[:90]

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Google アラート (RSS)",
        "items": all_items,
    }

    with open("alerts.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"alerts.json を出力しました(合計 {len(all_items)} 件)。", file=sys.stderr)


if __name__ == "__main__":
    main()
