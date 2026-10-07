$ErrorActionPreference='Stop'
$projectPath=[IO.Path]::GetFullPath($PSScriptRoot)
$expectedExe=Join-Path $projectPath 'bin\Debug\net10.0\GradeAcademica.exe'
Get-Process GradeAcademica -ErrorAction SilentlyContinue | Where-Object {$_.Path -eq $expectedExe} | Stop-Process
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' stop -D (Join-Path $projectPath '.local\pgdata') -m fast -w
Write-Output 'Aplicação e PostgreSQL deste projeto foram parados. Os dados foram preservados.'
