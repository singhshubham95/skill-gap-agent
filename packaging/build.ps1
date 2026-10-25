# Build the M29 Windows companion + per-user installer.
#
# Usage:
#   .\packaging\build.ps1
#   .\packaging\build.ps1 -SkipInstaller          # exe only (no Inno Setup)
#   .\packaging\build.ps1 -SkipSign               # local test build
#   .\packaging\build.ps1 -StoreUrl "https://chromewebstore.google.com/..."
#
# Signing (release builds): set SKILL_GAP_SIGN_PFX and
# SKILL_GAP_SIGN_PASSWORD (optionally SKILL_GAP_SIGNTOOL). Without a PFX
# the script produces an explicitly unsigned test build.

[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$InnoSetup = "",
    [string]$StoreUrl = $env:SKILL_GAP_STORE_URL,
    [switch]$SkipInstaller,
    [switch]$SkipSign
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DistDir = Join-Path $RepoRoot "dist"
$AppDir = Join-Path $DistDir "SkillGapAgent"
$AppExe = Join-Path $AppDir "SkillGapAgent.exe"
$SetupExe = Join-Path $DistDir "SkillGapAgent-Setup.exe"
$StoreUrl = ($StoreUrl | ForEach-Object { $_.Trim() }) | Select-Object -First 1
if ($StoreUrl -and -not $StoreUrl.StartsWith("https://")) {
    throw "StoreUrl must start with https:// (got: $StoreUrl)"
}

function Resolve-Python {
    param([string]$Requested)
    if ($Requested) {
        if (Test-Path -LiteralPath $Requested) {
            return (Resolve-Path -LiteralPath $Requested).Path
        }
        $cmd = Get-Command $Requested -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        throw "Python not found: $Requested"
    }
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python 3.11+ not found. Create .venv or pass -Python."
}

function Find-Iscc {
    param([string]$Requested)
    if ($Requested) {
        if (Test-Path -LiteralPath $Requested) {
            return (Resolve-Path -LiteralPath $Requested).Path
        }
        throw "ISCC.exe not found: $Requested"
    }
    if ($env:SKILL_GAP_ISCC) {
        if (Test-Path -LiteralPath $env:SKILL_GAP_ISCC) {
            return (Resolve-Path -LiteralPath $env:SKILL_GAP_ISCC).Path
        }
        throw "SKILL_GAP_ISCC points at a missing file: $env:SKILL_GAP_ISCC"
    }
    $candidates = @()
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
    }
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Inno Setup 6 not found. Install it (winget install JRSoftware.InnoSetup) or pass -InnoSetup."
}

function Find-SignTool {
    param([string]$Requested)
    if ($Requested) {
        if (Test-Path -LiteralPath $Requested) {
            return (Resolve-Path -LiteralPath $Requested).Path
        }
        throw "signtool.exe not found: $Requested"
    }
    if ($env:SKILL_GAP_SIGNTOOL) {
        if (Test-Path -LiteralPath $env:SKILL_GAP_SIGNTOOL) {
            return (Resolve-Path -LiteralPath $env:SKILL_GAP_SIGNTOOL).Path
        }
        throw "SKILL_GAP_SIGNTOOL points at a missing file: $env:SKILL_GAP_SIGNTOOL"
    }
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    if (${env:ProgramFiles(x86)}) {
        $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
        if (Test-Path -LiteralPath $kits) {
            $found = Get-ChildItem -LiteralPath $kits -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
                Sort-Object FullName -Descending |
                Select-Object -First 1
            if ($found) { return $found.FullName }
        }
    }
    throw "signtool.exe not found. Install the Windows SDK or set SKILL_GAP_SIGNTOOL."
}

$Python = Resolve-Python -Requested $Python

Push-Location $RepoRoot
try {
    $Version = (& $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $Version) { throw "Could not read the project version." }
    $ModuleVersion = (& $Python -c "from skill_gap_agent import __version__; print(__version__)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $ModuleVersion) { throw "Could not import skill_gap_agent.__version__." }
    if ($Version -ne $ModuleVersion) {
        throw "Version mismatch: pyproject=$Version package=$ModuleVersion"
    }

    & $Python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'PyInstaller is missing. Run: pip install -e ".[dev,desktop]" pyinstaller'
    }

    $Icon = Join-Path $PSScriptRoot "app.ico"
    if (-not (Test-Path -LiteralPath $Icon)) {
        & $Python (Join-Path $PSScriptRoot "make_icon.py")
        if ($LASTEXITCODE -ne 0) { throw "Could not generate packaging/app.ico." }
    }

    Write-Host "Building Skill-Gap Agent $Version (one-directory, windowed) ..."
    & $Python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "skill-gap-agent.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
    if (-not (Test-Path -LiteralPath $AppExe)) {
        throw "PyInstaller did not produce $AppExe"
    }

    $CanSign = $false
    $SignTool = $null
    $SignPfx = $env:SKILL_GAP_SIGN_PFX
    $SignPassword = $env:SKILL_GAP_SIGN_PASSWORD
    if (-not $SkipSign) {
        if ($SignPfx) {
            if (-not (Test-Path -LiteralPath $SignPfx)) {
                throw "SKILL_GAP_SIGN_PFX does not exist: $SignPfx"
            }
            $SignTool = Find-SignTool -Requested $env:SKILL_GAP_SIGNTOOL
            $CanSign = $true
        } else {
            Write-Warning "No SKILL_GAP_SIGN_PFX set: producing an UNSIGNED test build. Do not publish it."
        }
    } else {
        Write-Warning "Signing skipped (-SkipSign): unsigned test build."
    }

    if ($CanSign) {
        Write-Host "Signing the companion executable ..."
        $signArgs = @("sign", "/fd", "sha256", "/tr", "https://timestamp.digicert.com",
                      "/td", "sha256", "/f", $SignPfx)
        if ($SignPassword) { $signArgs += @("/p", $SignPassword) }
        $signArgs += $AppExe
        & $SignTool @signArgs
        if ($LASTEXITCODE -ne 0) { throw "Signing the companion executable failed." }
    }

    if (-not $SkipInstaller) {
        $Iscc = Find-Iscc -Requested $InnoSetup
        if (-not $StoreUrl) {
            Write-Warning "No SKILL_GAP_STORE_URL set: the installer will not open the Chrome Web Store."
        }
        $OpenStore = if ($StoreUrl) { "1" } else { "0" }
        $isccArgs = @(
            "/DAppVersion=$Version",
            "/DSourceDir=$AppDir",
            "/DOutputDir=$DistDir",
            "/DStoreUrl=$StoreUrl",
            "/DOpenStore=$OpenStore"
        )
        if ($CanSign) {
            $signCommand = '"' + $SignTool + '" sign /fd sha256 /tr https://timestamp.digicert.com /td sha256 /f "' + $SignPfx + '"'
            if ($SignPassword) { $signCommand += ' /p "' + $SignPassword + '"' }
            $signCommand += ' $f'
            $isccArgs = @("/DSigning=1", "/Sskillgap=$signCommand") + $isccArgs
        }
        $isccArgs += (Join-Path $PSScriptRoot "installer.iss")
        Write-Host "Compiling the per-user installer ..."
        & $Iscc @isccArgs
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }
        if (-not (Test-Path -LiteralPath $SetupExe)) {
            throw "Inno Setup did not produce $SetupExe"
        }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $SetupExe).Hash.ToLowerInvariant()
        "$hash  SkillGapAgent-Setup.exe" | Set-Content -LiteralPath "$SetupExe.sha256" -Encoding ascii
        Write-Host "Installer: $SetupExe"
        Write-Host "Checksum: $SetupExe.sha256"
    } else {
        Write-Host "App: $AppExe (installer skipped)"
    }

    if (-not $CanSign) {
        Write-Warning "Final artifact is UNSIGNED (test only)."
    }
    if (-not $StoreUrl -and -not $SkipInstaller) {
        Write-Warning "No Chrome Web Store URL was embedded (listing pending)."
    }
}
finally {
    Pop-Location
}
