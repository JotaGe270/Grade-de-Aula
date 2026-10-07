$ErrorActionPreference='Stop'
$settings=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'appsettings.Local.json') -Raw | ConvertFrom-Json
$csb=[System.Data.Common.DbConnectionStringBuilder]::new();$csb.set_ConnectionString($settings.ConnectionStrings.Postgres)
$previous=$env:PGPASSWORD
try {
 $env:PGPASSWORD=[string]$csb.get_Item('Password')
 $email=& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p $csb.get_Item('Port') -U grade_owner -d grade_academica -tAc "SELECT email FROM grade_app.usuario WHERE role='coordenador' ORDER BY id_usuario LIMIT 1"
 if($LASTEXITCODE -ne 0){throw 'Inicialize o sistema e faça uma primeira requisição de login para criar o esquema.'}
 $access=@{Email=$email.Trim();Password=$settings.Bootstrap.Password;Url='http://localhost:5049';Matricula=$email.Trim().Split('@')[0]}
 $file=Join-Path $PSScriptRoot '.local\acesso-inicial.json'
 $access | ConvertTo-Json | Set-Content -LiteralPath $file -Encoding utf8
 Write-Output "Acesso inicial salvo em $file. A senha é a inicial; alterações feitas no perfil não são refletidas neste arquivo."
} finally {$env:PGPASSWORD=$previous}
