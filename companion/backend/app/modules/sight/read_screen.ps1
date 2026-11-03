param([string]$ImagePath, [switch]$ListLanguages)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$languages = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Where-Object { $_.LanguageTag -match '^(zh|en|ja|ko)(-|$)' })
if ($ListLanguages) {
    ConvertTo-Json -InputObject @($languages | ForEach-Object { $_.LanguageTag }) -Compress
    exit
}
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1
} | Select-Object -First 1
function Await($Operation, $ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    $task.Result
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try {
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    try {
        $lines = @()
        $seen = @{}
        # Run one installed recognizer per script family, not just Windows UI language.
        $families = @{}
        foreach ($language in $languages) {
          $family = $language.LanguageTag.Split('-')[0]
          if ($families.ContainsKey($family)) { continue }
          $families[$family] = $true
          $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
          if ($null -eq $engine) { continue }
          $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
          $result.Lines | ForEach-Object {
            $line = $_
            $firstWord = $line.Words | Select-Object -First 1
            $signature = $line.Text + '|' + [int]($firstWord.BoundingRect.Y)
            if ($seen.ContainsKey($signature)) { return }
            $seen[$signature] = $true
            $words = @($line.Words | ForEach-Object { @{
                text = $_.Text; x = $_.BoundingRect.X; y = $_.BoundingRect.Y
                width = $_.BoundingRect.Width; height = $_.BoundingRect.Height
            } })
            $lines += @{ text = $line.Text; words = $words; language = $language.LanguageTag }
          }
        }
        ConvertTo-Json -InputObject $lines -Depth 6 -Compress
    } finally { $bitmap.Dispose() }
} finally { $stream.Dispose() }
