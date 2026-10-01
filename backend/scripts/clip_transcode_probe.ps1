<#
Measure what transcoding finalized rolling clips (MJPEG AVI) to H.264 MP4 costs and saves.

Read-only for the clips: outputs go to -OutDir (a temporary folder by default), never beside the
source. Runs in Windows PowerShell 5.1 or PowerShell 7 and needs only ffmpeg.exe, so it runs on the
robot PC beside a packaged RobotControl:

    powershell -ExecutionPolicy Bypass -File clip_transcode_probe.ps1 `
        -Ffmpeg "C:\RobotControl\ffmpeg.exe" -Clips "C:\RobotControl\data\videos\rolling_clips"

Each ffmpeg child runs at BelowNormal priority, as the product does. Reported per clip and profile:
output size, wall time, child CPU time (user + kernel), frame counts of source and output, SSIM and
PSNR against the source. One side-by-side PNG (source left, H.264 right) per profile is saved for
the first clip. A profile whose encoder is unavailable (h264_qsv / h264_mf without Intel graphics),
or a clip ffmpeg cannot read (a truncated recording), is reported as failed and the others continue. Results: results.csv in -OutDir.
#>
param(
    [string]$Ffmpeg = "",
    [Parameter(Mandatory = $true)][string]$Clips,
    [int]$Count = 6,
    [string[]]$Profiles = @("openh264-300", "openh264-600", "openh264-1000", "qsv-600", "mf-600"),
    [string]$OutDir = (Join-Path ([IO.Path]::GetTempPath()) ("clip-transcode-probe-" + (Get-Date -Format "yyyyMMdd-HHmmss"))),
    [int]$SampleFrame = 225
)
$ErrorActionPreference = "Stop"

if (-not $Ffmpeg) {
    $Ffmpeg = Join-Path $PSScriptRoot "..\..\build\vendor\ffmpeg\ffmpeg.exe"
}
$Ffmpeg = (Resolve-Path $Ffmpeg).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null

$common = @("-g", "75", "-bf", "0")
$profileArgs = @{
    "openh264-300"  = @("-c:v", "libopenh264", "-profile:v", "constrained_baseline", "-rc_mode", "bitrate", "-b:v", "300k", "-threads", "1", "-pix_fmt", "yuv420p")
    "openh264-600"  = @("-c:v", "libopenh264", "-profile:v", "constrained_baseline", "-rc_mode", "bitrate", "-b:v", "600k", "-threads", "1", "-pix_fmt", "yuv420p")
    "openh264-1000" = @("-c:v", "libopenh264", "-profile:v", "constrained_baseline", "-rc_mode", "bitrate", "-b:v", "1000k", "-threads", "1", "-pix_fmt", "yuv420p")
    "openh264-main-600" = @("-c:v", "libopenh264", "-profile:v", "main", "-coder", "cabac", "-rc_mode", "bitrate", "-b:v", "600k", "-threads", "1", "-pix_fmt", "yuv420p")
    "qsv-600"       = @("-c:v", "h264_qsv", "-b:v", "600k", "-maxrate", "600k")
    "mf-600"        = @("-c:v", "h264_mf", "-hw_encoding", "1", "-b:v", "600k", "-pix_fmt", "nv12")
}
# "-File" passes "a,b" as one string; accept both that and a real array.
$Profiles = @($Profiles | ForEach-Object { $_ -split "," } | Where-Object { $_ })
foreach ($name in $Profiles) { if (-not $profileArgs.ContainsKey($name)) { throw "Unknown profile $name" } }

function Invoke-Ffmpeg([string[]]$arguments, [switch]$Measure) {
    # Start-Process joins arguments with spaces, so quote any that contain one.
    $quoted = $arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
    $stdout = Join-Path $OutDir "ffmpeg-stdout.txt"
    $stderr = Join-Path $OutDir "ffmpeg-stderr.txt"
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath $Ffmpeg -ArgumentList $quoted -NoNewWindow -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $null = $process.Handle  # Windows PowerShell 5.1 loses ExitCode and CPU times without an open handle
    try { $process.PriorityClass = "BelowNormal" } catch { }
    $process.WaitForExit()
    $watch.Stop()
    [pscustomobject]@{
        ExitCode = $process.ExitCode
        Seconds  = $watch.Elapsed.TotalSeconds
        Cpu      = if ($Measure) { $process.TotalProcessorTime.TotalSeconds } else { 0 }
        Stdout   = [string](Get-Content -Raw $stdout)
        Stderr   = [string](Get-Content -Raw $stderr)
    }
}

function Get-FrameCount([string]$path) {
    # Counts packets without decoding; the product additionally decodes to verify.
    $run = Invoke-Ffmpeg @("-hide_banner", "-nostdin", "-v", "error", "-i", $path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-", "-progress", "pipe:1")
    $frames = [regex]::Matches([string]$run.Stdout, "frame=(\d+)") | Select-Object -Last 1
    if ($frames) { [int]$frames.Groups[1].Value } else { -1 }
}

$sources = Get-ChildItem -Path $Clips -Filter "clip_*.avi" |
    Where-Object { $_.Name -notlike "*.partial.*" } |
    Sort-Object LastWriteTime -Descending
$selected = @()
foreach ($clip in $sources) {
    if ($selected.Count -ge $Count) { break }
    if ((Get-FrameCount $clip.FullName) -gt 0) { $selected += $clip }  # skip clips ffmpeg cannot open at all
}
if (-not $selected) { throw "No complete clip_*.avi files in $Clips" }

$rows = @()
foreach ($clip in $selected) {
    $sourceFrames = Get-FrameCount $clip.FullName
    foreach ($name in $Profiles) {
        $output = Join-Path $OutDir ("{0}.{1}.mp4" -f $clip.BaseName, $name)
        $encode = Invoke-Ffmpeg (@("-hide_banner", "-nostdin", "-v", "error", "-y", "-i", $clip.FullName, "-map", "0:v:0", "-an",
            "-fps_mode", "passthrough") + $common + $profileArgs[$name] + @("-movflags", "+faststart", $output)) -Measure
        $row = [ordered]@{
            clip = $clip.Name; profile = $name; source_mb = [math]::Round($clip.Length / 1MB, 2)
            output_mb = $null; ratio = $null; wall_s = [math]::Round($encode.Seconds, 2); cpu_s = [math]::Round($encode.Cpu, 2)
            source_frames = $sourceFrames; output_frames = $null; ssim = $null; psnr_db = $null; error = ""
        }
        if ($encode.ExitCode -ne 0 -or -not (Test-Path $output)) {
            $row.error = ("exit {0}: {1}" -f $encode.ExitCode, $encode.Stderr.Trim()) -replace "\s+", " "
            if ($row.error.Length -gt 160) { $row.error = $row.error.Substring(0, 160) }
            $rows += [pscustomobject]$row
            Write-Host ("{0} {1}: FAILED {2}" -f $clip.Name, $name, $row.error)
            continue
        }
        $size = (Get-Item $output).Length
        $row.output_mb = [math]::Round($size / 1MB, 2)
        $row.ratio = [math]::Round($clip.Length / $size, 1)
        $row.output_frames = Get-FrameCount $output
        $quality = Invoke-Ffmpeg @("-hide_banner", "-nostdin", "-i", $output, "-i", $clip.FullName, "-lavfi",
            "[0:v]format=yuv420p,split[a][b];[1:v]format=yuv420p,split[c][d];[a][c]ssim;[b][d]psnr", "-f", "null", "-")
        $ssim = [regex]::Match([string]$quality.Stderr, "SSIM .*All:([\d.]+)")
        $psnr = [regex]::Match([string]$quality.Stderr, "PSNR .*average:([\d.inf]+)")
        if ($ssim.Success) { $row.ssim = [double]$ssim.Groups[1].Value }
        if ($psnr.Success) { $row.psnr_db = $psnr.Groups[1].Value }
        if ($clip -eq $selected[0]) {
            $png = Join-Path $OutDir ("side-by-side.{0}.png" -f $name)
            Invoke-Ffmpeg @("-hide_banner", "-nostdin", "-v", "error", "-y", "-i", $clip.FullName, "-i", $output, "-lavfi",
                "[0:v]select=eq(n\,$SampleFrame)[a];[1:v]select=eq(n\,$SampleFrame)[b];[a][b]hstack", "-frames:v", "1", "-update", "1", $png) | Out-Null
        }
        $rows += [pscustomobject]$row
        Write-Host ("{0} {1}: {2} MB -> {3} MB (x{4}), cpu {5} s, frames {6}/{7}, SSIM {8}" -f $clip.Name, $name,
            $row.source_mb, $row.output_mb, $row.ratio, $row.cpu_s, $row.output_frames, $row.source_frames, $row.ssim)
    }
}

$rows | Export-Csv -NoTypeInformation -Path (Join-Path $OutDir "results.csv")
Write-Host ""
Write-Host "Per-profile means:"
$rows | Where-Object { -not $_.error } | Group-Object profile | ForEach-Object {
    $group = $_.Group
    "{0,-18} {1,6:N2} MB/clip  x{2,5:N1}  cpu {3,5:N2} s/clip  SSIM {4:N4}  frames ok {5}/{6}" -f $_.Name,
        ($group | Measure-Object output_mb -Average).Average, ($group | Measure-Object ratio -Average).Average,
        ($group | Measure-Object cpu_s -Average).Average, ($group | Measure-Object ssim -Average).Average,
        @($group | Where-Object { $_.output_frames -eq $_.source_frames }).Count, $group.Count
} | Write-Host
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
Write-Host ("CPU: {0}, {1} logical processors. Output: {2}" -f $cpu.Name.Trim(), $cpu.NumberOfLogicalProcessors, $OutDir)
Remove-Item -ErrorAction SilentlyContinue (Join-Path $OutDir "ffmpeg-stdout.txt"), (Join-Path $OutDir "ffmpeg-stderr.txt")
