$ErrorActionPreference = "Stop"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python 3 required" }
if (-not (Get-Command npx -ErrorAction SilentlyContinue))    { throw "Node 18+ / npx required" }
$SkillDir = Join-Path $HOME ".claude/skills"
if (-not (Test-Path (Join-Path $SkillDir "seo"))) { throw "claude-seo not installed" }
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillTarget = Join-Path $SkillDir "seo-unlighthouse"
New-Item -ItemType Directory -Path $SkillTarget -Force | Out-Null
Copy-Item (Join-Path $SourceDir "skills/seo-unlighthouse/SKILL.md") `
          (Join-Path $SkillTarget "SKILL.md") -Force
& npx --yes --package=unlighthouse@0.13.5 unlighthouse-ci --help *> $null
Write-Host "Done."
