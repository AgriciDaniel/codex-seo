#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="${HOME}/.claude/skills/seo-bing"
SETTINGS_JSON="${HOME}/.claude/settings.json"
[ -d "${SKILL_DIR}" ] && rm -rf "${SKILL_DIR}" && echo "✓ Removed ${SKILL_DIR}"
if [ -f "${SETTINGS_JSON}" ]; then
  python3 - "${SETTINGS_JSON}" <<'PY'
import json, os, sys, tempfile
path = sys.argv[1]; data = json.load(open(path))
env = data.get("env", {})
removed = []
for k in ("BING_WEBMASTER_API_KEY", "INDEXNOW_KEY", "INDEXNOW_KEY_LOCATION"):
    if k in env:
        env.pop(k); removed.append(k)
if removed:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".settings.", suffix=".json")
    with os.fdopen(fd, "w") as fh: json.dump(data, fh, indent=2)
    os.chmod(tmp, 0o600); os.replace(tmp, path)
    print(f"✓ Cleared {', '.join(removed)}")
PY
fi
