<#
Measure what transcoding finalized rolling clips (MJPEG AVI) to H.264 MP4 costs and saves.

Read-only for the clips: outputs go to -OutDir (a temporary folder by default), never beside the
source. Runs in Windows PowerShell 5.1 or PowerShell 7 and needs only ffmpeg.exe, so it runs on the
robot PC beside a packaged RobotControl:

    powershell -ExecutionPolicy Bypass -File clip_transcode_probe.ps1 `
        -Ffmpeg "C:\RobotControl\ffmpeg.exe" -Clips "C:\RobotControl\data\videos\rolling_clips"

Each ffmpeg child runs at BelowNormal priority, as the product does. Reported per clip and profile:
output size, wall time, child CPU time (user + kernel), the child's peak CPU in cores and the whole
machine's peak CPU % (both over 250 ms windows, time-based like System status, not Task Manager's
frequency-scaled utility), frame counts of source and output, SSIM and PSNR against the source.
The "product" profiles run the conversion exactly as backend/services/clip_transcoder.py does,
including its verifying decode (verify_* columns); "product-1000-before" is the command before
2026-10-02, which left the decoder, filters and verifying decoder on their default thread counts;
"product-1000" is the conversion without denoise and "product-1000-denoise" with -DenoiseFilter
(default: CAMERA_CONFIG clip_denoise_filter as of 2026-10-05; pass the current value if it changed):

    powershell -ExecutionPolicy Bypass -File clip_transcode_probe.ps1 -Clips <folder> `
        -Profiles product-1000,product-1000-denoise -Count 8
 One side-by-side PNG (source left, H.264 right) per profile is saved for
the first clip. A profile whose encoder is unavailable (h264_qsv / h264_mf without Intel graphics),
or a clip ffmpeg cannot read (a truncated recording), is reported as failed and the others continue. Results: results.csv in -OutDir.
#>
param(
    [string]$Ffmpeg = "",
    [Parameter(Mandatory = $true)][string]$Clips,
    [int]$Count = 6,
    [string[]]$Profiles = @("openh264-300", "openh264-600", "openh264-1000", "qsv-600", "mf-600"),
    [string]$OutDir = (Join-Path ([IO.Path]::GetTempPath()) ("clip-transcode-probe-" + (Get-Date -Format "yyyyMMdd-HHmmss"))),
    [int]$SampleFrame = 225,
    [string]$DenoiseFilter = "atadenoise=0a=0.16:0b=0.32:1a=0.16:1b=0.32:2a=0.16:2b=0.32:s=7:a=s"
)
$ErrorActionPreference = "Stop"

if (-not $Ffmpeg) {
    $Ffmpeg = Join-Path $PSScriptRoot "..\..\build\vendor\ffmpeg\ffmpeg.exe"
}
$Ffmpeg = (Resolve-Path $Ffmpeg).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null

$common = @("-g", "75", "-bf", "0")
$singleThreaded = @("-threads", "1", "-filter_threads", "1")
$productEncode = @("-vf", "scale=out_range=tv,format=yuv420p", "-color_range", "tv", "-c:v", "libopenh264",
    "-profile:v", "constrained_baseline", "-rc_mode", "bitrate", "-b:v", "1000k", "-threads", "1")
$profileArgs = @{
    "openh264-300"  = @("-c:v", "libopenh264", "-profile:v", "constrained_baseline", "-rc_mode", "bitrate", "-b:v", "300k", "-threads", "1", "-pix_fmt", "yuv420p")
    "openh264-600"  = @("-c:v", "libopenh264", "-profile:v", "constrained_baseline", "-rc_mode", "bitrate", "-b:v", "600k", "-threads", "1", "-pix_fmt", "yuv420p")
    "openh264-1000" = @("-c:v", "libopenh264", "-profile:v", "constrained_baseline", "-rc_mode", "bitrate", "-b:v", "1000k", "-threads", "1", "-pix_fmt", "yuv420p")
    "openh264-main-600" = @("-c:v", "libopenh264", "-profile:v", "main", "-coder", "cabac", "-rc_mode", "bitrate", "-b:v", "600k", "-threads", "1", "-pix_fmt", "yuv420p")
    "qsv-600"       = @("-c:v", "h264_qsv", "-b:v", "600k", "-maxrate", "600k")
    "mf-600"        = @("-c:v", "h264_mf", "-hw_encoding", "1", "-b:v", "600k", "-pix_fmt", "nv12")
    "product-1000"  = $productEncode
    "product-1000-before" = $productEncode
    "product-1000-denoise" = @("-vf", "scale=out_range=tv,format=yuv420p,$DenoiseFilter") + $productEncode[2..($productEncode.Count - 1)]
}
# Placed before -i, for the encode and the verifying decode.
$inputArgs = @{ "product-1000" = $singleThreaded; "product-1000-denoise" = $singleThreaded; "product-1000-before" = @() }
# "-File" passes "a,b" as one string; accept both that and a real array.
$Profiles = @($Profiles | ForEach-Object { $_ -split "," } | Where-Object { $_ })
foreach ($name in $Profiles) { if (-not $profileArgs.ContainsKey($name)) { throw "Unknown profile $name" } }

Add-Type -Namespace ClipProbe -Name Native -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern bool GetSystemTimes(out long idle, out long kernel, out long user);
'@
function Get-MachineTimes {
    $idle = 0L; $kernel = 0L; $user = 0L
    [void][ClipProbe.Native]::GetSystemTimes([ref]$idle, [ref]$kernel, [ref]$user)
    [pscustomobject]@{ Busy = $kernel + $user - $idle; Total = $kernel + $user }  # kernel time includes idle
}

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
    $peakCores = 0.0; $peakMachine = 0.0
    $lastCpu = 0.0; $lastSeconds = 0.0; $lastMachine = Get-MachineTimes
    while (-not $process.WaitForExit(250)) {
        if (-not $Measure) { continue }
        $process.Refresh()
        try { $cpu = $process.TotalProcessorTime.TotalSeconds } catch { continue }  # exited between checks
        $seconds = $watch.Elapsed.TotalSeconds
        $machine = Get-MachineTimes
        $peakCores = [math]::Max($peakCores, ($cpu - $lastCpu) / ($seconds - $lastSeconds))
        if ($machine.Total -gt $lastMachine.Total) {
            $peakMachine = [math]::Max($peakMachine, 100 * ($machine.Busy - $lastMachine.Busy) / ($machine.Total - $lastMachine.Total))
        }
        $lastCpu = $cpu; $lastSeconds = $seconds; $lastMachine = $machine
    }
    $process.WaitForExit()
    $watch.Stop()
    [pscustomobject]@{
        ExitCode = $process.ExitCode
        Seconds  = $watch.Elapsed.TotalSeconds
        Cpu      = if ($Measure) { $process.TotalProcessorTime.TotalSeconds } else { 0 }
        PeakCores = $peakCores
        PeakMachine = $peakMachine
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

# Background load, so a machine peak below can be read against it.
$baseline = @(); $last = Get-MachineTimes
for ($i = 0; $i -lt 12; $i++) {
    Start-Sleep -Milliseconds 250
    $now = Get-MachineTimes
    $baseline += 100 * ($now.Busy - $last.Busy) / [math]::Max(1, $now.Total - $last.Total); $last = $now
}
$baselineText = "machine before the runs: mean {0:N0} %, peak {1:N0} % (250 ms windows)" -f
    ($baseline | Measure-Object -Average).Average, ($baseline | Measure-Object -Maximum).Maximum
Write-Host $baselineText

$rows = @()
foreach ($clip in $selected) {
    $sourceFrames = Get-FrameCount $clip.FullName
    foreach ($name in $Profiles) {
        $output = Join-Path $OutDir ("{0}.{1}.mp4" -f $clip.BaseName, $name)
        $leadingArgs = if ($inputArgs.ContainsKey($name)) { $inputArgs[$name] } else { @() }
        $encode = Invoke-Ffmpeg (@("-hide_banner", "-nostdin", "-v", "error", "-y") + $leadingArgs + @("-i", $clip.FullName, "-map", "0:v:0", "-an",
            "-fps_mode", "passthrough") + $common + $profileArgs[$name] + @("-movflags", "+faststart", $output)) -Measure
        $row = [ordered]@{
            clip = $clip.Name; profile = $name; source_mb = [math]::Round($clip.Length / 1MB, 2)
            output_mb = $null; ratio = $null; wall_s = [math]::Round($encode.Seconds, 2); cpu_s = [math]::Round($encode.Cpu, 2)
            peak_cores = [math]::Round($encode.PeakCores, 2); peak_machine_pct = [math]::Round($encode.PeakMachine)
            verify_wall_s = $null; verify_cpu_s = $null; verify_peak_cores = $null
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
        if ($inputArgs.ContainsKey($name)) {
            $verify = Invoke-Ffmpeg (@("-hide_banner", "-nostdin", "-loglevel", "error") + $leadingArgs +
                @("-i", $output, "-map", "0:v:0", "-f", "null", "-", "-progress", "pipe:1")) -Measure
            $row.verify_wall_s = [math]::Round($verify.Seconds, 2)
            $row.verify_cpu_s = [math]::Round($verify.Cpu, 2)
            $row.verify_peak_cores = [math]::Round($verify.PeakCores, 2)
        }
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
    $verifyCpu = ($group | Measure-Object verify_cpu_s -Average).Average
    "{0,-19} {1,6:N2} MB/clip  x{2,5:N1}  cpu {3,5:N2} s/clip (verify {4:N2})  wall {5:N2} s  peak {6:N2} cores, machine {7:N0} %  SSIM {8:N4}  frames ok {9}/{10}" -f $_.Name,
        ($group | Measure-Object output_mb -Average).Average, ($group | Measure-Object ratio -Average).Average,
        (($group | Measure-Object cpu_s -Average).Average + $verifyCpu), $verifyCpu,
        (($group | Measure-Object wall_s -Average).Average + ($group | Measure-Object verify_wall_s -Average).Average),
        ($group | Measure-Object peak_cores -Maximum).Maximum, ($group | Measure-Object peak_machine_pct -Maximum).Maximum,
        ($group | Measure-Object ssim -Average).Average,
        @($group | Where-Object { $_.output_frames -eq $_.source_frames }).Count, $group.Count
} | Write-Host
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
Write-Host ("CPU: {0}, {1} logical processors; {2}. Output: {3}" -f $cpu.Name.Trim(), $cpu.NumberOfLogicalProcessors, $baselineText, $OutDir)
Remove-Item -ErrorAction SilentlyContinue (Join-Path $OutDir "ffmpeg-stdout.txt"), (Join-Path $OutDir "ffmpeg-stderr.txt")
