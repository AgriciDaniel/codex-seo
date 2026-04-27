# DataForSEO Extension Uninstaller for Codex SEO (Windows)

$ErrorActionPreference = "Stop"

Write-Host "→ Uninstalling DataForSEO extension..." -ForegroundColor Yellow

$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$SkillsRoot = Join-Path $CodexRoot "skills"
$AgentDir = Join-Path $CodexRoot "agents"

# Remove skill
if (Test-Path (Join-Path $SkillsRoot "seo-dataforseo")) {
    Remove-Item -Recurse -Force (Join-Path $SkillsRoot "seo-dataforseo")
}

# Remove agent
$agentFile = Join-Path $AgentDir "seo-dataforseo.toml"
if (Test-Path $agentFile) {
    Remove-Item -Force $agentFile
}

# Remove field config
$fieldConfig = Join-Path $SkillsRoot "seo\dataforseo-field-config.json"
if (Test-Path $fieldConfig) {
    Remove-Item -Force $fieldConfig
}

# Remove MCP server entry from settings.json
$settingsFile = Join-Path $CodexRoot "settings.json"
if (Test-Path $settingsFile) {
    $python = Get-Command -Name python -ErrorAction SilentlyContinue
    if ($null -eq $python) {
        $python = Get-Command -Name py -ErrorAction SilentlyContinue
    }

    if ($null -ne $python) {
        $pyExe = $python.Source
        $pyScript = @"
import json
settings_path = r'$settingsFile'
with open(settings_path, 'r') as f:
    settings = json.load(f)
if 'mcpServers' in settings and 'dataforseo' in settings['mcpServers']:
    del settings['mcpServers']['dataforseo']
    if not settings['mcpServers']:
        del settings['mcpServers']
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
    print('  ok')
"@
        $result = & $pyExe -c $pyScript 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ Removed dataforseo from settings.json" -ForegroundColor Green
        } else {
            Write-Host "  ⚠  Could not auto-remove MCP config. Remove 'dataforseo' from ~\.codex\settings.json manually." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  ⚠  Python not found. Remove 'dataforseo' from ~\.codex\settings.json manually." -ForegroundColor Yellow
    }
}

Write-Host "✓ DataForSEO extension uninstalled." -ForegroundColor Green
