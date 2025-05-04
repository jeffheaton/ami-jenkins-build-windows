<#
  init.ps1  —  bootstrap a Windows Jenkins worker

  Must run as Admin. Uses Chocolatey for package installs, pyenv-win
  for Python version management, and configures Docker + build tools.
#>

# 0) ensure running as Administrator
If (-not ([Security.Principal.WindowsPrincipal]
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Error "This script must be run as Administrator."
  Exit 1
}

# 1) Install Chocolatey if missing
Set-ExecutionPolicy Bypass -Scope Process -Force
If (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
  Write-Host "Installing Chocolatey…"
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  iex ((New-Object Net.WebClient).DownloadString(
    'https://community.chocolatey.org/install.ps1'))
} Else {
  Write-Host "Chocolatey already installed."
}

# Refresh the session’s PATH
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine")

# 2) Core tooling via Chocolatey
choco install -y `
  temurin17 `       # Amazon-Corretto 17 equivalent
  git `
  pyenv-win `       # Python version manager for Windows
  docker-desktop `
  visualstudio2022buildtools

# 3) Start-on-login for Docker & add Jenkins user to docker-users group
& "C:\Program Files\Docker\Docker\DockerCli.exe" -SwitchDaemon
If (Get-LocalUser -Name 'Jenkins' -ErrorAction SilentlyContinue) {
  Add-LocalGroupMember -Group 'docker-users' -Member 'Jenkins'
}

# 4) Configure pyenv-win (machine-wide)
#    pyenv-win defaults to %USERPROFILE%\.pyenv but when installed via choco:
$pyenvRoot = "$Env:LOCALAPPDATA\pyenv\pyenv-win" 
[Environment]::SetEnvironmentVariable("PYENV","$pyenvRoot",'Machine')
$machinePath = [Environment]::GetEnvironmentVariable("Path","Machine")
$newPath = "$machinePath;${pyenvRoot}\bin;${pyenvRoot}\shims"
[Environment]::SetEnvironmentVariable("Path",$newPath,'Machine')
$env:Path = $newPath

# 5) Install & activate Python versions
#    -s: skip download if already present
pyenv install 3.12.0 -s
pyenv install 3.11.0 -s

# Set 3.12.0 as global default
pyenv global 3.12.0

# 6) Upgrade pip, install pipx, ensure it's on PATH
#    (will apply to whichever Python is currently active)
Write-Host "Upgrading pip & installing pipx…"
python -m pip install --upgrade pip pipx
python -m pipx ensurepath

# 7) Install Poetry and export plugin
Write-Host "Installing Poetry & export plugin…"
python -m pip install poetry
# make sure `poetry` is on PATH
& poetry --version
poetry self add poetry-plugin-export

Write-Host "Windows Jenkins agent bootstrap complete!"

