param(
    [string]$BackupPath = "data/backup/gis_kampus.backup",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
if (-not $Force) {
    throw "Obnavljanje zamenjuje sedam projektnih tabela. Ponovite komandu sa -Force kada ste sigurni."
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvPath = Join-Path $ProjectRoot ".env"
$ResolvedBackup = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $BackupPath))
$BackupRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "data/backup"))
if (-not $ResolvedBackup.StartsWith($BackupRoot + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Rezervna kopija mora biti unutar data/backup/."
}
if (-not (Test-Path -LiteralPath $ResolvedBackup)) {
    throw "Rezervna kopija ne postoji: $ResolvedBackup"
}

$Settings = @{}
foreach ($Line in Get-Content -LiteralPath $EnvPath -Encoding UTF8) {
    $Trimmed = $Line.Trim()
    if (-not $Trimmed -or $Trimmed.StartsWith("#")) { continue }
    $Parts = $Trimmed -split "=", 2
    if ($Parts.Count -eq 2) { $Settings[$Parts[0].Trim()] = $Parts[1].Trim().Trim('"').Trim("'") }
}
foreach ($Name in "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD") {
    if (-not $Settings.ContainsKey($Name) -or -not $Settings[$Name]) { throw "U .env fajlu nedostaje $Name." }
}
if ($Settings.DB_NAME -in @("postgres", "template0", "template1")) {
    throw "Zaštita je odbila obnavljanje sistemske baze $($Settings.DB_NAME)."
}

$Command = Get-Command pg_restore -ErrorAction SilentlyContinue
if ($Command) { $PgRestore = $Command.Source } else {
    $Candidates = Get-ChildItem -Path "$env:ProgramFiles\PostgreSQL\*\bin\pg_restore.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]$_.Directory.Parent.Name } -Descending
    if (-not $Candidates) { throw "Nije pronađen pg_restore. Proverite PostgreSQL instalaciju." }
    $PgRestore = $Candidates[0].FullName
}

Push-Location $ProjectRoot
try {
    python -m src.giscampus.sql.database
    if ($LASTEXITCODE -ne 0) { throw "Priprema baze nije uspela." }

    $env:PGPASSWORD = $Settings.DB_PASSWORD
    $RestoreArguments = @(
        "--host=$($Settings.DB_HOST)", "--port=$($Settings.DB_PORT)",
        "--username=$($Settings.DB_USER)", "--dbname=$($Settings.DB_NAME)",
        "--clean", "--if-exists", "--no-owner", "--no-privileges",
        $ResolvedBackup
    )
    & $PgRestore @RestoreArguments
    if ($LASTEXITCODE -ne 0) { throw "pg_restore nije uspešno obnovio bazu." }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host "Baza $($Settings.DB_NAME) je obnovljena iz: $ResolvedBackup"
Write-Host "Pokrenite: python scripts/check_setup.py"
