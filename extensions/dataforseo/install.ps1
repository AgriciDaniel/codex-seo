# DataForSEO Extension Installer for Codex SEO (Windows)
# PowerShell installation script

$ErrorActionPreference = "Stop"

Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "║   DataForSEO Extension - Installer   ║" -ForegroundColor Cyan
Write-Host "║   For Codex SEO                     ║" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$SkillsRoot = Join-Path $CodexRoot "skills"
$SeoSkillDir = Join-Path $SkillsRoot "seo"
if (-not (Test-Path $SeoSkillDir)) {
    Write-Host "✗ Codex SEO is not installed." -ForegroundColor Red
    Write-Host "  Install it first: irm https://raw.githubusercontent.com/AgriciDaniel/codex-seo/main/install.ps1 | iex"
    exit 1
}
Write-Host "✓ Codex SEO detected" -ForegroundColor Green

$nodeCmd = Get-Command -Name node -ErrorAction SilentlyContinue
if ($null -eq $nodeCmd) {
    Write-Host "✗ Node.js is required but not installed." -ForegroundColor Red
    Write-Host "  Install Node.js 20+: https://nodejs.org/"
    exit 1
}

$nodeVersion = (node -v) -replace 'v','' -split '\.' | Select-Object -First 1
if ([int]$nodeVersion -lt 20) {
    Write-Host "✗ Node.js 20+ required (found v$nodeVersion)." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Node.js $(node -v) detected" -ForegroundColor Green

$npxCmd = Get-Command -Name npx -ErrorAction SilentlyContinue
if ($null -eq $npxCmd) {
    Write-Host "✗ npx is required but not found (comes with npm)." -ForegroundColor Red
    exit 1
}
Write-Host "✓ npx detected" -ForegroundColor Green

# Prompt for credentials
Write-Host ""
Write-Host "DataForSEO API credentials required." -ForegroundColor Yellow
Write-Host "Sign up at: https://app.dataforseo.com/register"
Write-Host ""

$DfseUsername = Read-Host "DataForSEO username (email)"
if ([string]::IsNullOrEmpty($DfseUsername)) {
    Write-Host "✗ Username cannot be empty." -ForegroundColor Red
    exit 1
}

$DfsePasswordSecure = Read-Host "DataForSEO password" -AsSecureString
$DfsePassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DfsePasswordSecure)
)
if ([string]::IsNullOrEmpty($DfsePassword)) {
    Write-Host "✗ Password cannot be empty." -ForegroundColor Red
    exit 1
}

# Determine source directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRootCandidate = Resolve-Path (Join-Path $ScriptDir "..\..") -ErrorAction SilentlyContinue
$InstalledSkillCandidate = Resolve-Path (Join-Path $ScriptDir "..\..\..\seo-dataforseo\SKILL.md") -ErrorAction SilentlyContinue
if ($RepoRootCandidate -and (Test-Path (Join-Path $RepoRootCandidate.Path "skills\seo-dataforseo\SKILL.md"))) {
    $SkillSource = Join-Path $RepoRootCandidate.Path "skills\seo-dataforseo\SKILL.md"
    $AgentSource = Join-Path $RepoRootCandidate.Path "agents\seo-dataforseo.toml"
    $FieldConfigSource = Join-Path $ScriptDir "field-config.json"
} elseif ($InstalledSkillCandidate) {
    $SkillSource = $InstalledSkillCandidate.Path
    $AgentSource = Join-Path $CodexRoot "agents\seo-dataforseo.toml"
    $FieldConfigSource = Join-Path $ScriptDir "field-config.json"
} elseif (Test-Path "$ScriptDir\skills\seo-dataforseo\SKILL.md") {
    $SkillSource = "$ScriptDir\skills\seo-dataforseo\SKILL.md"
    $AgentSource = "$ScriptDir\agents\seo-dataforseo.toml"
    $FieldConfigSource = Join-Path $ScriptDir "field-config.json"
} else {
    Write-Host "✗ Cannot find extension source files." -ForegroundColor Red
    Write-Host "  Run this script from the codex-seo repo."
    exit 1
}

# Set paths
$SkillDir = Join-Path $SkillsRoot "seo-dataforseo"
$AgentDir = Join-Path $CodexRoot "agents"
$SettingsFile = Join-Path $CodexRoot "settings.json"
$FieldConfigPath = "$SeoSkillDir\dataforseo-field-config.json"

# Install skill
Write-Host ""
Write-Host "→ Installing DataForSEO skill..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null
Copy-Item -Force $SkillSource "$SkillDir\SKILL.md"

# Install agent
Write-Host "→ Installing DataForSEO agent..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
$AgentTarget = Join-Path $AgentDir "seo-dataforseo.toml"
if ($AgentSource -and (Test-Path $AgentSource) -and ((Resolve-Path $AgentSource).Path -ne $AgentTarget)) {
    Copy-Item -Force $AgentSource $AgentTarget
} elseif (Test-Path $AgentTarget) {
    Write-Host "  ✓ Codex TOML agent already installed" -ForegroundColor Green
} else {
    Write-Host "  ⚠  Codex TOML agent not found; reinstall the core Codex SEO suite if delegation is unavailable." -ForegroundColor Yellow
}

# Install field config
Write-Host "→ Installing field config..." -ForegroundColor Yellow
Copy-Item -Force $FieldConfigSource $FieldConfigPath

# Merge MCP config into settings.json
Write-Host "→ Configuring MCP server..." -ForegroundColor Yellow

$python = Get-Command -Name python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    $python = Get-Command -Name py -ErrorAction SilentlyContinue
}

if ($null -ne $python) {
    $pyExe = $python.Source
    $pyScript = @"
import json, os
settings_path = r'$SettingsFile'
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json.load(f)
else:
    settings = {}
if 'mcpServers' not in settings:
    settings['mcpServers'] = {}
settings['mcpServers']['dataforseo'] = {
    'command': 'npx',
    'args': ['-y', 'dataforseo-mcp-server'],
    'env': {
        'DATAFORSEO_USERNAME': '$DfseUsername',
        'DATAFORSEO_PASSWORD': '$DfsePassword',
        'ENABLED_MODULES': 'SERP,KEYWORDS_DATA,ONPAGE,DATAFORSEO_LABS,BACKLINKS,DOMAIN_ANALYTICS,BUSINESS_DATA,CONTENT_ANALYSIS,AI_OPTIMIZATION',
        'FIELD_CONFIG_PATH': r'$FieldConfigPath'
    }
}
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)
print('  ok')
"@

    $result = & $pyExe -c $pyScript 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ MCP server configured in settings.json" -ForegroundColor Green
    } else {
        Write-Host "  ⚠  Could not auto-configure MCP server." -ForegroundColor Yellow
        Write-Host "  Add the dataforseo server manually to ~\.codex\settings.json"
    }
} else {
    Write-Host "  ⚠  Python not found. Configure MCP server manually." -ForegroundColor Yellow
    Write-Host "  See: extensions\dataforseo\docs\DATAFORSEO-SETUP.md"
}

# Pre-warm npx package
Write-Host "→ Pre-downloading dataforseo-mcp-server..." -ForegroundColor Yellow
try {
    & npx -y dataforseo-mcp-server --help 2>&1 | Out-Null
} catch {
    # Ignore errors from pre-warm
}

Write-Host ""
Write-Host "✓ DataForSEO extension installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Usage:" -ForegroundColor Cyan
Write-Host "  1. Restart Codex CLI"
Write-Host "  2. Run commands:"
Write-Host "     /seo dataforseo serp best coffee shops"
Write-Host "     /seo dataforseo keywords seo tools"
Write-Host "     /seo dataforseo backlinks example.com"
Write-Host "     /seo dataforseo ai-mentions your brand"
Write-Host ""
Write-Host "All 22 commands: see extensions\dataforseo\README.md"
Write-Host "To uninstall: .\extensions\dataforseo\uninstall.ps1"
