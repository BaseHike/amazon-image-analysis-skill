# Windows built-in OCR (Windows.Media.Ocr) for check_excel.py.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr_images.ps1 <list.txt> <out.json>
#   list.txt: one image path per line (UTF-8). out.json: {"<path>": "<recognized text>", ...}
param([string]$ListFile, [string]$OutFile)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(); $task.Result }
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { throw 'no OCR language installed' }
$res = @{}
foreach ($p in [IO.File]::ReadAllLines($ListFile, [Text.Encoding]::UTF8)) {
    if (-not $p.Trim()) { continue }
    try {
        $f = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
        $s = Await ($f.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $d = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($s)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $b = Await ($d.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $r = Await ($engine.RecognizeAsync($b)) ([Windows.Media.Ocr.OcrResult])
        $res[$p] = $r.Text
        $s.Dispose()
    } catch { $res[$p] = $null }
}
[IO.File]::WriteAllText($OutFile, ($res | ConvertTo-Json -Depth 2), (New-Object Text.UTF8Encoding $false))
