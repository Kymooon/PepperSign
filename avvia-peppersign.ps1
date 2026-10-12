<#
.SYNOPSIS
    Avvia PepperSign con Docker rilevando automaticamente l'IP del PC.

.DESCRIPTION
    1. Rileva l'IP del PC sulla rete del robot:
         - hotspot di Windows attivo  -> 192.168.137.1
         - altrimenti                 -> IP della scheda con gateway (Wi-Fi/Ethernet)
    2. Lo passa a Caddy (PEPPERSIGN_HOST) per il certificato HTTPS.
       Il file .env NON viene modificato: il valore dello script ha la precedenza.
    3. Avvia i container con "docker compose up -d".

.PARAMETER Ip
    IP da usare al posto di quello rilevato (es. -Ip 192.168.0.50).

.PARAMETER Build
    Ricostruisce le immagini prima dell'avvio (dopo modifiche al codice).

.PARAMETER Services
    Servizi da avviare (default: tutti). Es. -Services web,process,caddy

.EXAMPLE
    .\avvia-peppersign.ps1
    .\avvia-peppersign.ps1 -Ip 192.168.0.50
    .\avvia-peppersign.ps1 -Services web,process,caddy
    .\avvia-peppersign.ps1 -Build
#>
param(
    [string]$Ip,
    [switch]$Build,
    [string[]]$Services
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Title($text) { Write-Host ""; Write-Host "== $text ==" -ForegroundColor Cyan }

# ---------- 1) Docker attivo? ----------
Write-Title "Controllo Docker"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker non risponde. Avvia Docker Desktop e attendi 'Engine running', poi riprova." -ForegroundColor Red
    exit 1
}
Write-Host "Docker OK"

if (-not (Test-Path ".env")) {
    Write-Host "ATTENZIONE: file .env non trovato. Copia .env.example in .env e imposta almeno PEPPER_IP." -ForegroundColor Yellow
}

# ---------- 2) Rilevamento IP ----------
Write-Title "Rilevamento IP del PC"

function Get-PepperSignHostIp {
    # a) Hotspot di Windows (rete tipica di Pepper): indirizzo fisso 192.168.137.1
    $hotspot = Get-NetIPAddress -AddressFamily IPv4 -IPAddress "192.168.137.1" -ErrorAction SilentlyContinue
    if ($hotspot) { return "192.168.137.1" }

    # b) Scheda attiva con gateway predefinito (Wi-Fi o Ethernet verso il router).
    #    Le schede virtuali (WSL, Hyper-V, VirtualBox, VPN) di solito non hanno gateway.
    $configs = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPv4DefaultGateway -and
            $_.NetAdapter.Status -eq "Up" -and
            $_.InterfaceAlias -notmatch "vEthernet|WSL|Hyper-V|VirtualBox|VMware|Loopback"
        } |
        Sort-Object { $_.IPv4Interface.InterfaceMetric }

    foreach ($cfg in $configs) {
        foreach ($addr in @($cfg.IPv4Address)) {
            if ($addr.IPAddress -and $addr.IPAddress -notlike "169.254.*") { return $addr.IPAddress }
        }
    }
    return $null
}

if ($Ip) {
    $hostIp = $Ip.Trim()
    Write-Host "IP indicato manualmente: $hostIp"
} else {
    $hostIp = Get-PepperSignHostIp
    if (-not $hostIp) {
        Write-Host "Impossibile rilevare l'IP. Rilancia indicandolo: .\avvia-peppersign.ps1 -Ip 192.168.x.x" -ForegroundColor Red
        Write-Host "Indirizzi IPv4 presenti:"
        Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" } |
            Format-Table InterfaceAlias, IPAddress -AutoSize
        exit 1
    }
    Write-Host "IP rilevato: $hostIp"
}

$env:PEPPERSIGN_HOST = $hostIp

# ---------- 3) Avvio container ----------
Write-Title "Avvio container"
$composeArgs = @("compose", "up", "-d")
if ($Build) { $composeArgs += "--build" }
if ($Services) { $composeArgs += ($Services | ForEach-Object { $_ -split "," } | Where-Object { $_ }) }

Write-Host ("docker " + ($composeArgs -join " "))
& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "Avvio non riuscito: controlla l'output qui sopra." -ForegroundColor Red
    exit $LASTEXITCODE
}

# ---------- 4) Riepilogo ----------
$httpsPort = "8443"
$httpPort = "8080"
$guiPort = "6080"
if (Test-Path ".env") {
    foreach ($line in Get-Content ".env") {
        if ($line -match "^\s*HTTPS_PORT\s*=\s*(\d+)") { $httpsPort = $Matches[1] }
        if ($line -match "^\s*WEB_HTTP_PORT\s*=\s*(\d+)") { $httpPort = $Matches[1] }
        if ($line -match "^\s*CONTROLL_GUI_PORT\s*=\s*(\d+)") { $guiPort = $Matches[1] }
    }
}

Write-Title "PepperSign avviato"
Write-Host "Tablet / altri dispositivi : https://${hostIp}:${httpsPort}/" -ForegroundColor Green
Write-Host "Da questo PC              : http://localhost:${httpPort}/PepperSign/"
Write-Host "GUI controller (robot)    : http://localhost:${guiPort}"
Write-Host ""
Write-Host "Al primo accesso HTTPS il browser mostra un avviso sul certificato: va accettato."
Write-Host "Se il tablet non si collega, apri la porta $httpsPort nel firewall di Windows."
Write-Host "Stato: docker compose ps   |   Log: docker compose logs -f process"
