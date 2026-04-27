# Firecrawl Extension Installer for Codex SEO (Windows)
$ErrorActionPreference = 'Stop'

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  Firecrawl Extension - Installer" -ForegroundColor Cyan
Write-Host "  For Codex SEO" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$SkillsRoot = Join-Path $CodexRoot "skills"
$SkillDir = Join-Path $SkillsRoot "seo-firecrawl"
$AgentDir = Join-Path $CodexRoot "agents"
$SeoSkillDir = Join-Path $SkillsRoot "seo"
$SettingsFile = Join-Path $CodexRoot "settings.json"

# Check prerequisites
if (-not (Test-Path $SeoSkillDir)) {
    Write-Host "x Codex SEO is not installed." -ForegroundColor Red
    Write-Host "  Install it first: irm https://raw.githubusercontent.com/AgriciDaniel/codex-seo/main/install.ps1 | iex"
    exit 1
}
Write-Host "v Codex SEO detected" -ForegroundColor Green

$nodeVersion = (node -v 2>$null) -replace 'v',''
if (-not $nodeVersion) {
    Write-Host "x Node.js is required but not installed." -ForegroundColor Red
    exit 1
}
$major = [int]($nodeVersion -split '\.')[0]
if ($major -lt 20) {
    Write-Host "x Node.js 20+ required (found v$nodeVersion)." -ForegroundColor Red
    exit 1
}
Write-Host "v Node.js v$nodeVersion detected" -ForegroundColor Green

# Prompt for API key
Write-Host ""
Write-Host "Firecrawl API key required." -ForegroundColor Yellow
Write-Host "Sign up at: https://www.firecrawl.dev/app/sign-up"
Write-Host "Free tier: 500 credits/month"
Write-Host ""

$apiKey = Read-Host "Firecrawl API key" -AsSecureString
$apiKeyPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($apiKey))
if ([string]::IsNullOrWhiteSpace($apiKeyPlain)) {
    Write-Host "x API key cannot be empty." -ForegroundColor Red
    exit 1
}

# Determine source directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRootCandidate = Resolve-Path (Join-Path $ScriptDir "..\..") -ErrorAction SilentlyContinue
$InstalledSkillCandidate = Resolve-Path (Join-Path $ScriptDir "..\..\..\seo-firecrawl\SKILL.md") -ErrorAction SilentlyContinue
if ($RepoRootCandidate -and (Test-Path (Join-Path $RepoRootCandidate.Path "skills\seo-firecrawl\SKILL.md"))) {
    $SkillSource = Join-Path $RepoRootCandidate.Path "skills\seo-firecrawl\SKILL.md"
    $AgentSource = Join-Path $RepoRootCandidate.Path "agents\seo-firecrawl.toml"
} elseif ($InstalledSkillCandidate) {
    $SkillSource = $InstalledSkillCandidate.Path
    $AgentSource = Join-Path $AgentDir "seo-firecrawl.toml"
} elseif (Test-Path "$ScriptDir\skills\seo-firecrawl\SKILL.md") {
    $SkillSource = "$ScriptDir\skills\seo-firecrawl\SKILL.md"
    $AgentSource = "$ScriptDir\agents\seo-firecrawl.toml"
} else {
    Write-Host "x Cannot find extension source files." -ForegroundColor Red
    exit 1
}

# Install skill
Write-Host ""
Write-Host "=> Installing Firecrawl skill..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null
Copy-Item $SkillSource "$SkillDir\SKILL.md" -Force

Write-Host "=> Installing Firecrawl agent..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
$AgentTarget = Join-Path $AgentDir "seo-firecrawl.toml"
if ($AgentSource -and (Test-Path $AgentSource) -and ((Resolve-Path $AgentSource).Path -ne $AgentTarget)) {
    Copy-Item $AgentSource $AgentTarget -Force
} elseif (Test-Path $AgentTarget) {
    Write-Host "  v Codex TOML agent already installed" -ForegroundColor Green
} else {
    Write-Host "  Warning: Codex TOML agent not found; reinstall the core Codex SEO suite if delegation is unavailable." -ForegroundColor Yellow
}

# Configure MCP server
Write-Host "=> Configuring MCP server..." -ForegroundColor Yellow
$settingsContent = if (Test-Path $SettingsFile) { Get-Content $SettingsFile -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
if (-not ($settingsContent.PSObject.Properties.Name -contains "mcpServers")) {
    $settingsContent | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) -Force
}
$settingsContent.mcpServers | Add-Member -NotePropertyName 'firecrawl-mcp' -NotePropertyValue @{
    command = 'npx'
    args = @('-y', 'firecrawl-mcp')
    env = @{ FIRECRAWL_API_KEY = $apiKeyPlain }
} -Force
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SettingsFile) | Out-Null
$settingsContent | ConvertTo-Json -Depth 10 | Set-Content $SettingsFile -Encoding UTF8
Write-Host "  v MCP server configured" -ForegroundColor Green

# Pre-warm
Write-Host "=> Pre-downloading firecrawl-mcp..." -ForegroundColor Yellow
npx -y firecrawl-mcp --help 2>$null | Out-Null

Write-Host ""
Write-Host "v Firecrawl extension installed!" -ForegroundColor Green
Write-Host ""
Write-Host "Usage:"
Write-Host "  /seo firecrawl crawl https://example.com"
Write-Host "  /seo firecrawl map https://example.com"
Write-Host "  /seo firecrawl scrape https://example.com/page"
