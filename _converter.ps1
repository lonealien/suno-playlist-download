# _converter.ps1
# Worker de conversão M4A -> MP3 com barra de progresso.
# Chamado pelo converter_mp3.bat. Não execute direto.

param(
    [Parameter(Mandatory=$true)][string]$Pasta
)

$ErrorActionPreference = "Continue"

# ---------------- Localiza ffmpeg ----------------
$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) {
    $alt = Join-Path $env:LOCALAPPDATA "ffmpeg\bin\ffmpeg.exe"
    if (Test-Path $alt) { $ffmpeg = $alt }
}
if (-not $ffmpeg) {
    Write-Host "  [X] ffmpeg nao encontrado." -ForegroundColor Red
    exit 2
}

$ffprobe = Join-Path (Split-Path $ffmpeg) "ffprobe.exe"
if (-not (Test-Path $ffprobe)) {
    $ffprobe = (Get-Command ffprobe -ErrorAction SilentlyContinue).Source
}

# ---------------- Lista arquivos .m4a ----------------
$m4as = @(Get-ChildItem -LiteralPath $Pasta -Filter *.m4a -File -ErrorAction SilentlyContinue)
if ($m4as.Count -eq 0) {
    Write-Host "  [i] Nenhum arquivo .m4a nesta pasta. Pulando." -ForegroundColor Yellow
    exit 0
}

$total = $m4as.Count
$num   = 0
$conv  = 0
$skip  = 0
$fail  = 0

# ---------------- Loop principal ----------------
foreach ($m4a in $m4as) {
    $num++
    $mp3 = [System.IO.Path]::ChangeExtension($m4a.FullName, ".mp3")
    $nome = $m4a.BaseName
    if ($nome.Length -gt 48) { $nomeCurto = $nome.Substring(0,45) + "..." } else { $nomeCurto = $nome }

    Write-Host ""
    Write-Host ("  [{0}/{1}] {2}" -f $num, $total, $nomeCurto) -ForegroundColor Cyan

    # Já existe MP3 -> apaga o m4a órfão e pula
    if (Test-Path -LiteralPath $mp3) {
        Remove-Item -LiteralPath $m4a.FullName -Force -ErrorAction SilentlyContinue
        $skip++
        Write-Host "        [=] ja existia MP3 - m4a apagado" -ForegroundColor DarkGray
        continue
    }

    # ---------------- Duração via ffprobe ----------------
    $dur = 0.0
    if ($ffprobe) {
        try {
            $durStr = & $ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 -- $m4a.FullName 2>$null
            if ($durStr) {
                $dur = [double]::Parse($durStr, [System.Globalization.CultureInfo]::InvariantCulture)
            }
        } catch { $dur = 0.0 }
    }
    if ($dur -le 0) { $dur = 180.0 }

    # ---------------- Monta comando ffmpeg ----------------
    $ffargs = @(
        "-y", "-loglevel", "quiet",
        "-i", $m4a.FullName,
        "-vn", "-map", "0:a:0",
        "-codec:a", "libmp3lame",
        "-b:a", "128k",
        "-compression_level", "0",
        "-threads", "0",
        "-progress", "pipe:1",
        "-nostats",
        $mp3
    )

    $argLine = ($ffargs | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"' + ($_ -replace '"','\"') + '"'
        } else { $_ }
    }) -join " "

    # ---------------- Processo ----------------
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $ffmpeg
    $psi.Arguments              = $argLine
    $psi.UseShellExecute        = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.CreateNoWindow         = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8

    $proc = [System.Diagnostics.Process]::Start($psi)

    # Drena stderr em background pra não travar
    $errTask = $proc.StandardError.ReadToEndAsync()

    $lastPct   = -1
    $barLen    = 32
    $startTime = Get-Date
    $linhaLen  = 0

    while (-not $proc.StandardOutput.EndOfStream) {
        $line = $proc.StandardOutput.ReadLine()
        if ($line -match '^out_time_ms=(-?\d+)') {
            $ms = [long]$matches[1]
            if ($ms -lt 0) { $ms = 0 }
            $sec = $ms / 1000000.0
            $pct = [int](($sec / $dur) * 100)
            if ($pct -gt 99) { $pct = 99 }
            if ($pct -ne $lastPct) {
                $lastPct = $pct
                $fill = [int]($pct * $barLen / 100)
                if ($fill -lt 0) { $fill = 0 }
                $bar = ("#" * $fill) + ("-" * ($barLen - $fill))

                $cur = [TimeSpan]::FromSeconds($sec)
                $tot = [TimeSpan]::FromSeconds($dur)
                $elapsed = (Get-Date) - $startTime
                if ($elapsed.TotalSeconds -gt 0) {
                    $speed = $sec / $elapsed.TotalSeconds
                } else { $speed = 0 }

                $linha = "        [{0}] {1,3}%  {2:mm\:ss}/{3:mm\:ss}  x{4:0.0}" -f `
                         $bar, $pct, $cur, $tot, $speed

                Write-Host -NoNewline "`r$linha"
                $linhaLen = $linha.Length
            }
        }
    }

    $proc.WaitForExit()
    $null = $errTask.Result

    # ---------------- Verifica resultado ----------------
    $ok = (Test-Path -LiteralPath $mp3) -and ((Get-Item -LiteralPath $mp3).Length -gt 1000)

    $fillFull = "#" * $barLen
    $final = "        [{0}] 100%  OK" -f $fillFull
    if ($final.Length -lt $linhaLen) {
        $final = $final.PadRight($linhaLen)
    }

    if ($ok) {
        Remove-Item -LiteralPath $m4a.FullName -Force -ErrorAction SilentlyContinue
        $conv++
        Write-Host -NoNewline "`r$final"
        Write-Host ""
    } else {
        $fail++
        $failMsg = "        [X] falhou - m4a mantido"
        if ($failMsg.Length -lt $linhaLen) { $failMsg = $failMsg.PadRight($linhaLen) }
        Write-Host -NoNewline "`r$failMsg"
        Write-Host ""
    }
}

Write-Host ""
Write-Host ("  Resultado: {0} convertidas | {1} ja existiam | {2} falhas" -f $conv, $skip, $fail) -ForegroundColor Green