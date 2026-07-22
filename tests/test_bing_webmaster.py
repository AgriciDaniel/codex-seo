"""Bounded Bing Webmaster link regressions for issue #153."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bing_webmaster as bing  # noqa: E402


def ok(data, endpoint="test"):
    return {
        "status": "success", "data": data, "error": None,
        "metadata": {"source": "bing_webmaster", "endpoint": endpoint, "timestamp": "now"},
    }


def error(message="failed"):
    return {"status": "error", "data": None, "error": message, "metadata": {"source": "bing_webmaster"}}


def count_page(page, total=2):
    return {"d": {"Links": [{"Url": f"https://site.test/p{page}", "Count": page + 2}], "TotalPages": total}}


def detail_page(page, total=2, source=None):
    source = source or f"https://Ref.Example/path{page}?private=value"
    return {"d": {"Details": [{"Url": source, "AnchorText": "anchor"}], "TotalPages": total}}


def test_link_counts_pages_to_documented_total():
    calls = []

    def request(endpoint, _key, params):
        calls.append((endpoint, params["page"]))
        return ok(count_page(params["page"], total=2), endpoint)

    with patch.object(bing, "_bing_request", side_effect=request):
        result = bing.get_link_counts("https://site.test/", "placeholder")
    assert result["status"] == "success"
    assert result["data"]["pages_fetched"] == 2
    assert result["data"]["sampled_inbound_link_count"] == 5
    assert result["data"]["complete"] is True
    assert calls == [("GetLinkCounts", 0), ("GetLinkCounts", 1)]


def test_link_counts_cap_is_explicitly_partial():
    with patch.object(bing, "_bing_request", return_value=ok(count_page(0, total=5))):
        result = bing.get_link_counts("https://site.test/", "placeholder", max_pages=1)
    assert result["status"] == "partial"
    assert result["data"]["complete"] is False
    assert result["data"]["warnings"]


def test_link_counts_later_failure_preserves_partial_data():
    def request(_endpoint, _key, params):
        return ok(count_page(0, total=2)) if params["page"] == 0 else error()

    with patch.object(bing, "_bing_request", side_effect=request):
        result = bing.get_link_counts("https://site.test/", "placeholder")
    assert result["status"] == "partial"
    assert result["data"]["pages_fetched"] == 1
    assert result["data"]["complete"] is False


def test_link_counts_first_failure_is_propagated():
    with patch.object(bing, "_bing_request", return_value=error("access denied")):
        result = bing.get_link_counts("https://site.test/", "placeholder")
    assert result["status"] == "error"
    assert result["error"] == "access denied"


def test_link_details_expands_bounded_pages_and_deduplicates():
    calls = []

    def request(endpoint, _key, params):
        calls.append((endpoint, params["page"]))
        if endpoint == "GetLinkCounts":
            return ok({"d": {"Links": [{"Url": "https://site.test/target?x=secret", "Count": 9}], "TotalPages": 1}})
        return ok(detail_page(params["page"], total=2, source="https://www.Ref.Example/a?token=secret"))

    with patch.object(bing, "_bing_request", side_effect=request):
        result = bing.get_link_details("https://site.test/", "placeholder", max_detail_pages=2)
    assert result["status"] == "success"
    assert result["data"]["complete"] is True
    assert result["data"]["total_returned"] == 1
    dumped = json.dumps(result)
    assert "secret" not in dumped
    assert result["data"]["links"][0]["source_url"] == "https://www.ref.example/a"
    assert calls == [("GetLinkCounts", 0), ("GetUrlLinks", 0), ("GetUrlLinks", 1)]


def test_link_details_partial_failure_is_not_hollow_success():
    def request(endpoint, _key, params):
        if endpoint == "GetLinkCounts":
            return ok({"d": {"Links": [
                {"Url": "https://site.test/a", "Count": 4},
                {"Url": "https://site.test/b", "Count": 3},
            ], "TotalPages": 1}})
        if params["link"].endswith("a"):
            return ok(detail_page(0, total=1))
        return error()

    with patch.object(bing, "_bing_request", side_effect=request):
        result = bing.get_link_details("https://site.test/", "placeholder")
    assert result["status"] == "partial"
    assert result["data"]["links"]
    assert result["data"]["partial_errors"] == [{"target_url": "https://site.test/b", "page": 0}]


def test_link_details_all_expansions_fail_as_error():
    def request(endpoint, _key, _params):
        if endpoint == "GetLinkCounts":
            return ok({"d": {"Links": [{"Url": "https://site.test/a", "Count": 4}], "TotalPages": 1}})
        return error()

    with patch.object(bing, "_bing_request", side_effect=request):
        result = bing.get_link_details("https://site.test/", "placeholder")
    assert result["status"] == "error"
    assert result["data"] is None


def test_link_details_rejects_invalid_caps_without_request():
    with patch.object(bing, "_bing_request") as request:
        result = bing.get_link_details("https://site.test/", "placeholder", page=-1)
    assert result["status"] == "error"
    request.assert_not_called()


def test_link_details_marks_unvisited_count_pages_partial():
    with patch.object(
        bing,
        "_bing_request",
        side_effect=[
            ok({"d": {"Links": [{"Url": "https://site.test/a", "Count": 4}], "TotalPages": 3}}),
            ok(detail_page(0, total=1)),
        ],
    ):
        result = bing.get_link_details("https://site.test/", "placeholder")
    assert result["status"] == "partial"
    assert result["data"]["complete"] is False


def test_verified_property_comparison_propagates_second_side_failure():
    first = ok({"complete": True, "links": []})
    with patch.object(bing, "get_link_details", side_effect=[first, error()]):
        result = bing.compare_links("https://a.test", "https://b.test", "placeholder")
    assert result["status"] == "error"
    assert "second property" in result["error"]


def test_verified_property_comparison_normalizes_referring_hosts():
    first = ok({"complete": True, "links": [{"source_url": "https://www.Shared.test/a"}]})
    second = ok({"complete": True, "links": [
        {"source_url": "https://shared.test/b"},
        {"source_url": "https://only.test/c"},
    ]})
    with patch.object(bing, "get_link_details", side_effect=[first, second]):
        result = bing.compare_links("https://a.test", "https://b.test", "placeholder")
    assert result["status"] == "success"
    assert result["data"]["shared_domains"] == ["shared.test"]
    assert result["data"]["gap_domains"] == ["only.test"]


def test_bing_request_does_not_mutate_caller_params():
    params = {"siteUrl": "https://site.test/", "page": 0}
    response = Mock(status_code=200, text="{}")
    response.json.return_value = {}

    with patch.object(bing, "_rate_limit"), patch.object(
        bing.requests, "get", return_value=response
    ) as request:
        result = bing._bing_request("GetLinkCounts", "placeholder", params)

    assert result["status"] == "success"
    assert params == {"siteUrl": "https://site.test/", "page": 0}
    sent_params = request.call_args.kwargs["params"]
    assert sent_params is not params
    assert sent_params == {"siteUrl": "https://site.test/", "page": 0, "apikey": "placeholder"}


def test_runtime_request_error_is_generic_and_contains_no_parameters():
    marker = "placeholder-secret-marker"

    def fail(*_args, **_kwargs):
        raise bing.requests.exceptions.ConnectionError(
            f"https://ssl.bing.test/?apikey={marker}&siteUrl=https://private.test/?token=value"
        )

    with patch.object(bing, "_rate_limit"), patch.object(bing.requests, "get", side_effect=fail):
        result = bing._bing_request("GetLinkCounts", marker, {"siteUrl": "https://private.test/?token=value"})
    dumped = json.dumps(result)
    assert marker not in dumped
    assert "token=value" not in dumped
    assert result["error"] == "Bing Webmaster request failed (ConnectionError)"


@pytest.mark.parametrize(
    ("argv", "expected_error"),
    [
        (["bing_webmaster.py", "counts", "https://user:pass@blocked.test/?token=value", "--json"],
         "Invalid or blocked target URL"),
        (["bing_webmaster.py", "counts", "user:pass@blocked.test/?token=value", "--json"],
         "Invalid or blocked target URL"),
        (["bing_webmaster.py", "compare", "site.test",
          "https://user:pass@blocked.test/?token=value", "--json"],
         "Invalid or blocked competitor URL"),
    ],
)
def test_cli_invalid_url_errors_do_not_echo_userinfo_or_query(
    argv, expected_error, capsys
):
    with patch.object(sys, "argv", argv), patch.object(
        bing, "validate_url", side_effect=lambda url: url == "https://site.test"
    ):
        with pytest.raises(SystemExit) as exc:
            bing.main()

    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert expected_error in output
    assert "user:pass" not in output
    assert "token=value" not in output


def test_removed_endpoints_are_absent_from_runtime_script():
    source = (ROOT / "scripts" / "bing_webmaster.py").read_text(encoding="utf-8")
    removed = "Get" + "LinkDetails"
    misused = "Get" + "UrlTrafficInfo"
    assert removed not in source
    assert misused not in source
