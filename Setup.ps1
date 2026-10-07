param([int]$DatabasePort=55432,[int]$WebPort=5049,[switch]$StartApp)
$ErrorActionPreference='Stop'
function New-LocalPassword([int]$length){
    $bytes=New-Object byte[] $length
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try {$rng.GetBytes($bytes)} finally {$rng.Dispose()}
    return [BitConverter]::ToString($bytes).Replace('-','')
}
$projectDir=$PSScriptRoot
$localDir=Join-Path $projectDir '.local'
$dataDir=Join-Path $localDir 'pgdata'
$pgBin='C:\Program Files\PostgreSQL\18\bin'
if(!(Test-Path (Join-Path $pgBin 'initdb.exe'))){throw 'PostgreSQL 18 não encontrado. Ajuste pgBin em Setup.ps1.'}
New-Item -ItemType Directory -Path $localDir -Force | Out-Null
$settingsFile=Join-Path $projectDir 'appsettings.Local.json'
if(Test-Path $settingsFile){$settings=Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json}
else {
    $dbPassword=New-LocalPassword 24
    $adminPassword=New-LocalPassword 12
    $settings=@{ConnectionStrings=@{Postgres="Host=127.0.0.1;Port=$DatabasePort;Database=grade_academica;Username=grade_owner;Password=$dbPassword"};Bootstrap=@{Name='Coordenador';Password=$adminPassword}}
    $settings | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $settingsFile -Encoding utf8
}
$csb=[System.Data.Common.DbConnectionStringBuilder]::new();$csb.set_ConnectionString($settings.ConnectionStrings.Postgres)
$dbPassword=[string]$csb.get_Item('Password');$DatabasePort=[int]$csb.get_Item('Port')
if(!(Test-Path (Join-Path $dataDir 'PG_VERSION'))){
    $pwFile=Join-Path $localDir 'init-password.tmp'
    try {
        Set-Content -LiteralPath $pwFile -Value $dbPassword -Encoding ascii
        & (Join-Path $pgBin 'initdb.exe') -D $dataDir -U grade_owner --auth=scram-sha-256 --encoding=UTF8 --locale=C --pwfile=$pwFile
        if($LASTEXITCODE -ne 0){throw 'Falha ao inicializar o PostgreSQL isolado.'}
    } finally {if(Test-Path $pwFile){Remove-Item -LiteralPath $pwFile}}
}
& (Join-Path $pgBin 'pg_ctl.exe') status -D $dataDir | Out-Null
if($LASTEXITCODE -ne 0){
    & (Join-Path $pgBin 'pg_ctl.exe') start -D $dataDir -l (Join-Path $localDir 'postgres.log') -o "-p $DatabasePort -h 127.0.0.1" -w
    if($LASTEXITCODE -ne 0){throw 'Falha ao iniciar PostgreSQL. Confira .local/postgres.log.'}
}
$oldPassword=$env:PGPASSWORD
try {
    $env:PGPASSWORD=$dbPassword
    $exists=& (Join-Path $pgBin 'psql.exe') -h 127.0.0.1 -p $DatabasePort -U grade_owner -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='grade_academica'"
    if($LASTEXITCODE -ne 0){throw 'Falha na conexão.'}
    if($exists -ne '1'){
        & (Join-Path $pgBin 'createdb.exe') -h 127.0.0.1 -p $DatabasePort -U grade_owner grade_academica
        if($LASTEXITCODE -ne 0){throw 'Falha ao criar banco.'}
    }
} finally {$env:PGPASSWORD=$oldPassword}
Write-Output "Banco pronto: 127.0.0.1:$DatabasePort / grade_academica. Credenciais em appsettings.Local.json (não versionar)."
if($StartApp){
    $running=$null
    try {$running=Invoke-RestMethod "http://localhost:$WebPort/api/status" -TimeoutSec 2} catch {}
    if($running.application -eq 'GradeAcademica'){& (Join-Path $projectDir 'GetAccess.ps1');Write-Output "Sistema já está rodando em http://localhost:$WebPort";return}
    $process=Start-Process -FilePath dotnet -ArgumentList "run --no-launch-profile --urls http://localhost:$WebPort" -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $localDir 'web.log') -RedirectStandardError (Join-Path $localDir 'web-error.log') -PassThru
    Write-Output "Sistema: http://localhost:$WebPort (PID $($process.Id))"
    $ready=$false
    for($attempt=0;$attempt -lt 25;$attempt++){
        try {$response=Invoke-RestMethod "http://localhost:$WebPort/api/status" -TimeoutSec 2;if($response.application -eq 'GradeAcademica'){$ready=$true;break}} catch {}
        Start-Sleep -Seconds 1
    }
    if(!$ready){throw 'Sistema não iniciou. Confira .local/web-error.log.'}
    & (Join-Path $projectDir 'GetAccess.ps1')
}
