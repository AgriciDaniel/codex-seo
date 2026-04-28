# Codex SEO Installer for Windows
# PowerShell installation script

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Codex SEO - Installer" -ForegroundColor Cyan
Write-Host "  Codex Skill Suite" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

function Resolve-Python {
    $pythonCmd = Get-Command -Name python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCmd) {
        return @{ Exe = "python"; Args = @() }
    }

    $pyCmd = Get-Command -Name py -ErrorAction SilentlyContinue
    if ($null -ne $pyCmd) {
        return @{ Exe = "py"; Args = @("-3") }
    }

    return $null
}

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $true)][string[]]$Args,
        [switch]$Quiet
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process `
            -FilePath $Exe `
            -ArgumentList $Args `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        $stdout = if (Test-Path $stdoutPath) { Get-Content -Path $stdoutPath -Raw } else { "" }
        $stderr = if (Test-Path $stderrPath) { Get-Content -Path $stderrPath -Raw } else { "" }
        $combined = @($stdout, $stderr) -join ""
        $output = if ([string]::IsNullOrWhiteSpace($combined)) { @() } else { $combined -split "`r?`n" }
        $exitCode = $process.ExitCode
    } finally {
        Remove-Item -Force $stdoutPath, $stderrPath -ErrorAction SilentlyContinue
    }

    if (-not $Quiet -and $null -ne $output -and $output.Count -gt 0) {
        $output | ForEach-Object { Write-Host $_ }
    }

    return @{ ExitCode = $exitCode; Output = $output }
}

function Test-Truthy {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    return @("1", "true", "yes", "on") -contains $Value.Trim().ToLowerInvariant()
}

function Get-JsonObjectText {
    param([string[]]$Output)

    $text = ($Output -join "`n").Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        return ""
    }

    $start = $text.IndexOf("{")
    $end = $text.LastIndexOf("}")
    if ($start -ge 0 -and $end -gt $start) {
        return $text.Substring($start, $end - $start + 1).Trim()
    }

    return $text
}

function ConvertFrom-JsonCompat {
    param(
        [Parameter(Mandatory = $true)][string]$Json,
        [Parameter(Mandatory = $true)][string]$ErrorMessage
    )

    try {
        return $Json | ConvertFrom-Json
    } catch {
        $preview = $Json
        if ($preview.Length -gt 1200) {
            $preview = $preview.Substring(0, 1200) + "`n...[truncated]"
        }
        Write-Host "[ERROR] $ErrorMessage" -ForegroundColor Red
        Write-Host "[ERROR] PowerShell JSON parser error: $($_.Exception.Message)" -ForegroundColor Red
        if (-not [string]::IsNullOrWhiteSpace($preview)) {
            Write-Host "[ERROR] Bootstrap output preview:" -ForegroundColor Red
            Write-Host $preview
        }
        throw $ErrorMessage
    }
}

function Remove-PathIfExists {
    param([string]$Path)

    if (Test-Path $Path) {
        Remove-Item -Path $Path -Recurse -Force
    }
}

$python = Resolve-Python
if ($null -eq $python) {
    Write-Host "[ERROR] Python 3 is required but was not found in PATH." -ForegroundColor Red
    exit 1
}

try {
    $pythonVersionOutput = (& $python.Exe @($python.Args + @("--version")) 2>&1 | Select-Object -Last 1).ToString().Trim()
} catch {
    Write-Host "[ERROR] Failed to determine Python version." -ForegroundColor Red
    exit 1
}

if ($pythonVersionOutput -notmatch "Python\s+(\d+)\.(\d+)") {
    Write-Host "[ERROR] Failed to parse Python version from: $pythonVersionOutput" -ForegroundColor Red
    exit 1
}

$pythonMajor = [int]$Matches[1]
$pythonMinor = [int]$Matches[2]
$pythonVersion = "$pythonMajor.$pythonMinor"
if ($pythonMajor -lt 3 -or ($pythonMajor -eq 3 -and $pythonMinor -lt 10)) {
    Write-Host "[ERROR] Python 3.10+ is required but $pythonVersion was found." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Python $pythonVersion detected" -ForegroundColor Green

$gitCmd = Get-Command -Name git -ErrorAction SilentlyContinue
if ($null -eq $gitCmd) {
    Write-Host "[ERROR] Git is required but not installed." -ForegroundColor Red
    exit 1
}

$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$skillsRoot = Join-Path $codexRoot "skills"
$agentDir = Join-Path $codexRoot "agents"
$skillDir = Join-Path $skillsRoot "seo"
$repoUrl = if ($env:CODEX_SEO_REPO) { $env:CODEX_SEO_REPO } else { "https://github.com/AgriciDaniel/codex-seo" }
$repoRef = if ($env:CODEX_SEO_REF) { $env:CODEX_SEO_REF } else { "v1.9.6-codex.3" }
$skipPlaywrightBrowser = Test-Truthy $env:CODEX_SEO_SKIP_PLAYWRIGHT_BROWSER
$playwrightWithDeps = Test-Truthy $env:CODEX_SEO_PLAYWRIGHT_WITH_DEPS
$suiteSkillDirs = @(
    "seo",
    "seo-audit",
    "seo-backlinks",
    "seo-cluster",
    "seo-competitor-pages",
    "seo-content",
    "seo-dataforseo",
    "seo-drift",
    "seo-ecommerce",
    "seo-flow",
    "seo-firecrawl",
    "seo-geo",
    "seo-google",
    "seo-hreflang",
    "seo-image-gen",
    "seo-images",
    "seo-local",
    "seo-maps",
    "seo-page",
    "seo-performance",
    "seo-plan",
    "seo-programmatic",
    "seo-schema",
    "seo-sitemap",
    "seo-sxo",
    "seo-technical",
    "seo-visual"
)

New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $agentDir | Out-Null

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
try {
    $checkoutDir = Join-Path $tempDir "codex-seo"

    Write-Host "[INFO] Downloading Codex SEO ($repoRef)..." -ForegroundColor Yellow
    $cloneResult = Invoke-External -Exe "git" -Args @("clone", "--depth", "1", "--branch", $repoRef, $repoUrl, $checkoutDir)
    if ($cloneResult.ExitCode -ne 0) {
        throw "Unable to download ref $repoRef. Confirm the branch/tag exists and your Git credentials can access $repoUrl."
    }

    $commitResult = Invoke-External -Exe "git" -Args @("-C", $checkoutDir, "rev-parse", "HEAD") -Quiet
    if ($commitResult.ExitCode -ne 0 -or $commitResult.Output.Count -eq 0) {
        throw "Unable to resolve the installed Codex SEO commit."
    }
    $installedCommit = $commitResult.Output[0].Trim()

    Write-Host "[INFO] Resetting existing Codex SEO install..." -ForegroundColor Yellow
    foreach ($suiteName in $suiteSkillDirs) {
        Remove-PathIfExists -Path (Join-Path $skillsRoot $suiteName)
    }
    Get-ChildItem -Path $agentDir -Filter "seo-*.md" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $agentDir -Filter "seo-*.toml" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

    Write-Host "[INFO] Installing skill files..." -ForegroundColor Yellow

    $skillsSource = Join-Path $checkoutDir "skills"
    if (Test-Path $skillsSource) {
        Get-ChildItem -Path $skillsSource -Directory | ForEach-Object {
            $target = Join-Path $skillsRoot $_.Name
            New-Item -ItemType Directory -Force -Path $target | Out-Null
            Copy-Item -Path (Join-Path $_.FullName "*") -Destination $target -Recurse -Force
        }
    }

    foreach ($pathName in @("scripts", "schema", "pdf", "hooks", "extensions")) {
        $sourcePath = Join-Path $checkoutDir $pathName
        if (Test-Path $sourcePath) {
            $targetPath = Join-Path $skillDir $pathName
            New-Item -ItemType Directory -Force -Path $targetPath | Out-Null
            Copy-Item -Path (Join-Path $sourcePath "*") -Destination $targetPath -Recurse -Force
        }
    }

    foreach ($doc in @("requirements.txt", "CHANGELOG.md", "README.md")) {
        $sourceDoc = Join-Path $checkoutDir $doc
        if (Test-Path $sourceDoc) {
            Copy-Item -Path $sourceDoc -Destination (Join-Path $skillDir $doc) -Force
        }
    }

    Write-Host "[INFO] Installing agent profiles..." -ForegroundColor Yellow
    $agentsSource = Join-Path $checkoutDir "agents"
    if (Test-Path $agentsSource) {
        Copy-Item -Path (Join-Path $agentsSource "*.toml") -Destination $agentDir -Force
    }

    $bootstrapScript = Join-Path $skillDir "scripts\bootstrap_environment.py"
    if (-not (Test-Path $bootstrapScript)) {
        throw "Bootstrap script was not installed to $bootstrapScript."
    }

    Write-Host "[INFO] Bootstrapping Python runtime..." -ForegroundColor Yellow
    $bootstrapArgs = @()
    $bootstrapArgs += $python.Args
    $bootstrapArgs += @(
        $bootstrapScript,
        "--venv",
        (Join-Path $skillDir ".venv"),
        "--json"
    )
    if ($skipPlaywrightBrowser) {
        $bootstrapArgs += "--skip-playwright-browser"
    }
    if ($playwrightWithDeps) {
        $bootstrapArgs += "--with-deps"
    }

    $bootstrapResult = Invoke-External -Exe $python.Exe -Args $bootstrapArgs -Quiet
    $bootstrapJson = Get-JsonObjectText -Output $bootstrapResult.Output
    if ([string]::IsNullOrWhiteSpace($bootstrapJson)) {
        throw "Bootstrap script did not produce JSON output."
    }

    $bootstrapPayload = ConvertFrom-JsonCompat -Json $bootstrapJson -ErrorMessage "Bootstrap script produced invalid JSON output."

    if ($bootstrapResult.ExitCode -ne 0 -or -not $bootstrapPayload.ok) {
        $verificationNotes = @()
        if ($null -ne $bootstrapPayload.verification -and $null -ne $bootstrapPayload.verification.notes) {
            $verificationNotes = @($bootstrapPayload.verification.notes)
        }
        if ($verificationNotes.Count -gt 0) {
            $verificationNotes | ForEach-Object { Write-Host "[ERROR] $_" -ForegroundColor Red }
        }
        throw "Codex SEO runtime bootstrap failed."
    }

    if (-not $bootstrapPayload.full_ready) {
        Write-Host "[WARN] Core SEO workflows are ready, but Playwright Chromium is not fully available yet. Visual analysis and premium PDF generation remain limited until browser installation succeeds." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "[OK] Codex SEO installed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Commit: $installedCommit"
    Write-Host "Installed to: $skillDir"
    Write-Host "Agents installed to: $agentDir"
    Write-Host "Python runtime: $($bootstrapPayload.python)"
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Restart Codex CLI if it is already running"
    Write-Host "  2. Verify the runtime: $($bootstrapPayload.python) $skillDir\scripts\verify_environment.py"
    Write-Host "  3. Ask Codex to use the SEO skill for an audit or content task"
    Write-Host ""
} finally {
    if (Test-Path $tempDir) {
        Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
