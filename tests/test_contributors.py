"""Attribution consistency for the 2026 issue and pull-request review cycle."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRIBUTORS = ROOT / "CONTRIBUTORS.md"

EXPECTED_HANDLES = {
    "DreaminginAI",
    "wonsukchoi",
    "powehi-ai",
    "maticyorg",
    "GilboBlagins",
    "voipcomjohn",
    "MSADTP",
    "lukababu",
    "kuhlsnu",
    "SENTMarketing",
    "BubblyWolf",
    "mubashirsidiki",
    "mukulcodezz",
    "us",
    "sam-fakhreddine",
    "n-youn9",
    "jonathanlombi-debug",
    "sohilshrestha0",
    "Kickermax",
    "Arul-Raaj",
    "atahan150",
    "maulikvora",
    "fayerman-source",
}


def test_review_cycle_human_contributors_are_credited_by_public_handle():
    text = CONTRIBUTORS.read_text(encoding="utf-8")
    linked_handles = set(
        re.findall(r"\[@([A-Za-z0-9-]+)\]\(https://github\.com/\1\)", text)
    )
    assert EXPECTED_HANDLES <= linked_handles


def test_contributors_file_contains_no_email_addresses_or_mail_links():
    text = CONTRIBUTORS.read_text(encoding="utf-8")
    assert "mailto:" not in text.lower()
    assert re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text) is None


def test_review_cycle_excludes_bots_and_promotional_only_issue():
    text = CONTRIBUTORS.read_text(encoding="utf-8")
    assert "dependabot" not in text.lower()
    assert "/issues/155" not in text
