# Firecrawl Extension Uninstaller for Codex SEO (Windows)
$ErrorActionPreference = 'Stop'

Write-Host "Removing Firecrawl extension..." -ForegroundColor Yellow

$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$SkillsRoot = Join-Path $CodexRoot "skills"
$AgentDir = Join-Path $CodexRoot "agents"
$SkillDir = Join-Path $SkillsRoot "seo-firecrawl"
$SettingsFile = Join-Path $CodexRoot "settings.json"

if (Test-Path $SkillDir) {
    Remove-Item -Recurse -Force $SkillDir
    Write-Host "v Removed skill files" -ForegroundColor Green
}

$AgentFile = Join-Path $AgentDir "seo-firecrawl.toml"
if (Test-Path $AgentFile) {
    Remove-Item -Force $AgentFile
    Write-Host "v Removed agent profile" -ForegroundColor Green
}

if (Test-Path $SettingsFile) {
    $settings = Get-Content $SettingsFile -Raw | ConvertFrom-Json
    if (($settings.PSObject.Properties.Name -contains "mcpServers") -and ($settings.mcpServers.PSObject.Properties.Name -contains "firecrawl-mcp")) {
        $settings.mcpServers.PSObject.Properties.Remove('firecrawl-mcp')
        $settings | ConvertTo-Json -Depth 10 | Set-Content $SettingsFile -Encoding UTF8
        Write-Host "v Removed MCP server from settings.json" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "v Firecrawl extension uninstalled." -ForegroundColor Green
Write-Host "  Core Codex SEO skills are unchanged."
