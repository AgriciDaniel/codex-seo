#!/usr/bin/env python3
"""
Probe an OpenAI-compatible Responses API provider for Codex-style readiness.

Usage:
    python scripts/test_openai_responses_provider.py \
        --base-url https://api.kie.ai/api/v1/responses \
        --api-key-env KIE_API_KEY \
        --model gpt-5.1-codex \
        --json
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from typing import Any

import requests


DEFAULT_TOOL_COMMAND = "python scripts/run_skill_workflow.py --skill seo-page https://www.python.org --json"
DEFAULT_LOOP_COMMAND = 'python -c "print(12345)"'


def post_json(url: str, api_key: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """POST JSON to an OpenAI-compatible Responses endpoint."""
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    try:
        data = response.json()
    except ValueError:
        data = {"raw_text": response.text}
    return response.status_code, data


def extract_output_text(response_json: dict[str, Any]) -> str | None:
    """Extract the first assistant output_text from a responses payload."""
    for item in response_json.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text")
    return None


def extract_function_call(response_json: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the first function_call entry from a responses payload."""
    for item in response_json.get("output", []):
        if item.get("type") == "function_call":
            return item
    return None


def command_argv(command: str) -> list[str]:
    """Parse a command into argv for shell-free execution."""
    argv = shlex.split(command)
    if not argv:
        raise ValueError("Command is empty.")
    return argv


def run_local_command(command: str, expected_command: str | None = None) -> dict[str, Any]:
    """Execute a local command for tool-loop probing without a shell."""
    try:
        argv = command_argv(command)
        if expected_command is not None and argv != command_argv(expected_command):
            raise ValueError("Emitted command did not match the expected command exactly.")
    except ValueError as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "ok": False,
            "error": f"Blocked unsafe command: {exc}",
        }

    completed = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=120)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }


def build_function_tool() -> dict[str, Any]:
    """Return a generic shell tool schema."""
    return {
        "type": "function",
        "name": "run_shell_command",
        "description": "Run a shell command in the workspace and return stdout/stderr",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    }


def probe_provider(
    base_url: str,
    api_key: str,
    model: str,
    reasoning_effort: str,
    tool_command: str,
    loop_command: str,
) -> dict[str, Any]:
    """Run live provider probes for text response, function call, and tool loop."""
    summary: dict[str, Any] = {
        "base_url": base_url,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "tests": {},
    }

    text_payload = {
        "model": model,
        "stream": False,
        "reasoning": {"effort": reasoning_effort},
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": 'Return exactly this JSON and nothing else: {"ok":true,"provider_probe":"text"}',
                    }
                ],
            }
        ],
    }
    text_status, text_response = post_json(base_url, api_key, text_payload)
    text_output = extract_output_text(text_response)
    summary["tests"]["text_response"] = {
        "http_status": text_status,
        "ok": text_status == 200 and bool(text_output),
        "output_text": text_output,
        "raw_status": text_response.get("status"),
    }

    function_payload = {
        "model": model,
        "stream": False,
        "reasoning": {"effort": reasoning_effort},
        "tool_choice": "auto",
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Use the run_shell_command tool to run exactly: {tool_command} . Do not answer normally.",
                    }
                ],
            }
        ],
        "tools": [build_function_tool()],
    }
    function_status, function_response = post_json(base_url, api_key, function_payload)
    function_call = extract_function_call(function_response)
    summary["tests"]["function_call"] = {
        "http_status": function_status,
        "ok": function_status == 200 and function_call is not None,
        "function_call": function_call,
        "assistant_output": extract_output_text(function_response),
    }

    loop_prompt_payload = {
        "model": model,
        "stream": False,
        "reasoning": {"effort": reasoning_effort},
        "tool_choice": "auto",
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"Use the run_shell_command tool to run exactly: {loop_command} . "
                            "After you receive tool output, answer with only the text TOOL_LOOP_OK: <result>."
                        ),
                    }
                ],
            }
        ],
        "tools": [build_function_tool()],
    }
    loop_step1_status, loop_step1_response = post_json(base_url, api_key, loop_prompt_payload)
    loop_call = extract_function_call(loop_step1_response)
    if loop_step1_status != 200 or loop_call is None:
        summary["tests"]["tool_loop"] = {
            "ok": False,
            "step1_http_status": loop_step1_status,
            "error": "Provider did not emit a function_call for loop probe.",
            "step1_response": loop_step1_response,
        }
        summary["overall_ok"] = all(test["ok"] for test in summary["tests"].values())
        return summary

    loop_command_actual = json.loads(loop_call["arguments"])["command"]
    local_execution = run_local_command(loop_command_actual, expected_command=loop_command)
    loop_step2_payload = {
        "model": model,
        "previous_response_id": loop_step1_response.get("id"),
        "stream": False,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "function_call_output",
                        "call_id": loop_call["call_id"],
                        "output": local_execution["stdout"] if local_execution["stdout"] else local_execution["stderr"],
                    }
                ],
            }
        ],
    }
    loop_step2_status, loop_step2_response = post_json(base_url, api_key, loop_step2_payload)
    loop_text = extract_output_text(loop_step2_response)
    summary["tests"]["tool_loop"] = {
        "ok": loop_step1_status == 200 and local_execution["ok"] and loop_step2_status == 200 and bool(loop_text),
        "step1_http_status": loop_step1_status,
        "step2_http_status": loop_step2_status,
        "emitted_command": loop_command_actual,
        "local_execution": {
            "ok": local_execution["ok"],
            "returncode": local_execution["returncode"],
            "stdout": local_execution["stdout"],
            "stderr": local_execution["stderr"],
            "error": local_execution.get("error"),
        },
        "final_output_text": loop_text,
        "step2_response": loop_step2_response,
    }

    summary["overall_ok"] = all(test["ok"] for test in summary["tests"].values())
    return summary


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Probe an OpenAI-compatible Responses provider for Codex-style readiness")
    parser.add_argument("--base-url", required=True, help="Responses endpoint URL")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Environment variable containing the API key")
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--reasoning-effort", default="medium", help="Reasoning effort")
    parser.add_argument("--tool-command", default=DEFAULT_TOOL_COMMAND, help="Command to request in the function-call probe")
    parser.add_argument("--loop-command", default=DEFAULT_LOOP_COMMAND, help="Command to use for the full tool-loop probe")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"Missing API key env var: {args.api_key_env}")
    api_key = "".join(api_key.split())

    result = probe_provider(
        base_url=args.base_url,
        api_key=api_key,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        tool_command=args.tool_command,
        loop_command=args.loop_command,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"Provider: {result['base_url']}")
    print(f"Model: {result['model']}")
    print(f"Overall OK: {'YES' if result['overall_ok'] else 'NO'}")
    for name, test in result["tests"].items():
        print(f"- {name}: {'OK' if test['ok'] else 'FAIL'}")


if __name__ == "__main__":
    main()
