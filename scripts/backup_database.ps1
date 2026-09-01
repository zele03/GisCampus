param(
    [string]$OutputPath = "data/backup/gis_kampus.backup",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvPath = Join-Path $ProjectRoot ".env"

function Read-ProjectEnvironment {
    if (-not (Test-Path -LiteralPath $EnvPath)) {
        throw "Nedostaje .env fajl. Napravite ga na osnovu .env.example."
    }

    $Values = @{}
    foreach ($Line in Get-Content -LiteralPath $EnvPath -Encoding UTF8) {
        $Trimmed = $Line.Trim()
        if (-not $Trimmed -or $Trimmed.StartsWith("#")) { continue }
        $Parts = $Trimmed -split "=", 2
        if ($Parts.Count -eq 2) {
            $Values[$Parts[0].Trim()] = $Parts[1].Trim().Trim('"').Trim("'")
        }
    }

    foreach ($Name in "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD") {
        if (-not $Values.ContainsKey($Name) -or -not $Values[$Name]) {
            throw "U .env fajlu nedostaje vrednost $Name."
        }
    }
    return $Values
}

function Find-PostgreSqlTool([string]$Name) {
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }

    $Candidates = Get-ChildItem -Path "$env:ProgramFiles\PostgreSQL\*\bin\$Name.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]$_.Directory.Parent.Name } -Descending
    if ($Candidates) { return $Candidates[0].FullName }
    throw "Nije pronađen $Name. Proverite da li je PostgreSQL instaliran."
}

$Settings = Read-ProjectEnvironment
$PgDump = Find-PostgreSqlTool "pg_dump"
$ResolvedOutput = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $OutputPath))
$BackupRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "data/backup"))
if (-not $ResolvedOutput.StartsWith($BackupRoot + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Rezervna kopija mora biti unutar data/backup/."
}
if ((Test-Path -LiteralPath $ResolvedOutput) -and -not $Force) {
    throw "Rezervna kopija već postoji. Ponovite sa -Force ako želite da je zamenite."
}

New-Item -ItemType Directory -Path (Split-Path $ResolvedOutput) -Force | Out-Null
$Tables = @(
    "zone_kampusa", "zgrade", "parkiralista", "zelene_povrsine",
    "infrastrukturni_objekti", "tereni", "ml_zgrade"
)
$Arguments = @(
    "--host=$($Settings.DB_HOST)", "--port=$($Settings.DB_PORT)",
    "--username=$($Settings.DB_USER)", "--dbname=$($Settings.DB_NAME)",
    "--format=custom", "--no-owner", "--no-privileges", "--file=$ResolvedOutput"
)
foreach ($Table in $Tables) { $Arguments += "--table=public.$Table" }

$env:PGPASSWORD = $Settings.DB_PASSWORD
try {
    & $PgDump @Arguments
    if ($LASTEXITCODE -ne 0) { throw "pg_dump nije uspešno napravio rezervnu kopiju." }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host "Rezervna kopija je napravljena: $ResolvedOutput"
