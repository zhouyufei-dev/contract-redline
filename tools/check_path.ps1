# Simulate a freshly opened terminal: rebuild PATH from the registry, then
# check which python.exe wins.
$machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$user = [Environment]::GetEnvironmentVariable('Path', 'User')
$env:Path = $machine + ';' + $user

Write-Output '--- python --version ---'
& python --version 2>&1
Write-Output '--- resolved path ---'
(Get-Command python -ErrorAction SilentlyContinue).Source
Write-Output '--- pip ---'
& python -m pip --version 2>&1
