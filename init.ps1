<#
  init.ps1 — bootstrap a Windows Jenkins worker (Python-first)
  Run under SSM as Administrator. No reboots; Sysprep happens later.
#>

$ErrorActionPreference = 'Stop'

# --- Helpers -----------------------------------------------------------------
function Assert-Admin {
  $isAdmin = ([Security.Principal.WindowsPrincipal]
    [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $isAdmin) { throw "This script must run as Administrator." }
}

function Add-MachinePathSegment {
  param([Parameter(Mandatory)][string]$Segment)
  $segNorm = $Segment.TrimEnd('\')
  $mPath   = [Environment]::GetEnvironmentVariable('Path','Machine')
  if ($mPath -split ';' | Where-Object { $_.TrimEnd('\') -ieq $segNorm }) { return }
  [Environment]::SetEnvironmentVariable('Path', "$mPath;$Segment", 'Machine')
  $env:Path = "$env:Path;$Segment"   # update current process too
}

function Test-PendingReboot {
  $keys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending',
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired',
    'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\PendingFileRenameOperations'
  )
  foreach ($k in $keys) { if (Test-Path $k) { return $true } }
  return $false
}

Assert-Admin

# --- Chocolatey --------------------------------------------------------------
Set-ExecutionPolicy Bypass -Scope Process -Force
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
  Write-Host "Installing Chocolatey..."
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  iex ((New-Object Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
} else {
  Write-Host "Chocolatey already installed."
}
choco feature enable -n=allowGlobalConfirmation

# --- Core tooling (no Docker) -----------------------------------------------
# Choose ONE JDK; using Amazon Corretto 17 to mirror Linux builds
$packages = @(
  'amazon-corretto17',
  'git',
  '7zip',
  'vcredist140',
  'pyenv-win'
)
foreach ($p in $packages) { choco install $p --no-progress }

# pyenv-win typical Chocolatey location
$pyenvRoot = 'C:\tools\pyenv\pyenv-win'
if (-not (Test-Path $pyenvRoot)) {
  # fallback for non-choco installs
  $maybe = Join-Path $env:USERPROFILE '.pyenv\pyenv-win'
  if (Test-Path $maybe) { $pyenvRoot = $maybe }
}
[Environment]::SetEnvironmentVariable('PYENV', $pyenvRoot, 'Machine')
[Environment]::SetEnvironmentVariable('PYENV_HOME', $pyenvRoot, 'Machine')
[Environment]::SetEnvironmentVariable('PYENV_ROOT', $pyenvRoot, 'Machine')
Add-MachinePathSegment "$pyenvRoot\bin"
Add-MachinePathSegment "$pyenvRoot\shims"

# --- Python versions via pyenv-win -------------------------------------------
# Pin current patch levels; adjust as desired
$py312 = '3.12.5'
$py311 = '3.11.9'

pyenv --version | Out-Null
pyenv update | Out-Null

pyenv install $py312 -s
pyenv install $py311 -s
pyenv global  $py312
pyenv rehash

# --- Pip / Poetry -------------------------------------------------------------
python -m pip install --upgrade pip setuptools wheel
python -m pip install "poetry<2.0" poetry-plugin-export
pyenv rehash
poetry --version | Write-Host
poetry self show plugins | Out-Null

# --- (Optional) Visual Studio Build Tools for native extensions --------------
# Uncomment if your projects compile C/C++ extensions. Leaves a pending reboot.
# choco install visualstudio2022buildtools --no-progress `
#   --package-parameters "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --quiet --norestart --locale en-US"

if (Test-PendingReboot) {
  Write-Warning "A reboot is pending (from installs). Sysprep may fail until reboot is applied."
}

Write-Host "Windows Jenkins agent bootstrap complete."
