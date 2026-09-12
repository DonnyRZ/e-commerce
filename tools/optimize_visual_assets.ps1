param(
  [string]$Source = "artifacts\imagegen\generated",
  [string]$Destination = "artifacts\imagegen\optimized",
  [int]$Quality = 88,
  [int]$MaxWidth = 1600,
  [int]$MaxHeight = 1200
)

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Drawing.Common -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$jpegCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
  Where-Object { $_.MimeType -eq "image/jpeg" } |
  Select-Object -First 1

foreach ($file in Get-ChildItem -LiteralPath $Source -Filter *.png -File) {
  $input = $null
  $bitmap = $null
  $canvas = $null
  $graphics = $null
  $stream = $null
  try {
    $input = [System.Drawing.Image]::FromFile($file.FullName)
    $scale = [Math]::Min(1.0, [Math]::Min($MaxWidth / $input.Width, $MaxHeight / $input.Height))
    $width = [Math]::Max(1, [int][Math]::Round($input.Width * $scale))
    $height = [Math]::Max(1, [int][Math]::Round($input.Height * $scale))
    $bitmap = [System.Drawing.Bitmap]::new($width, $height)
    $canvas = [System.Drawing.Graphics]::FromImage($bitmap)
    $canvas.Clear([System.Drawing.Color]::White)
    $canvas.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $canvas.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $canvas.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $canvas.DrawImage($input, 0, 0, $width, $height)

    $parameters = [System.Drawing.Imaging.EncoderParameters]::new(1)
    $parameters.Param[0] = [System.Drawing.Imaging.EncoderParameter]::new(
      [System.Drawing.Imaging.Encoder]::Quality, [long]$Quality
    )
    $output = Join-Path $Destination ($file.BaseName + ".jpg")
    $bitmap.Save($output, $jpegCodec, $parameters)
    Write-Output "$($file.Name) -> $([IO.Path]::GetFileName($output))"
  } finally {
    if ($graphics) { $graphics.Dispose() }
    if ($canvas) { $canvas.Dispose() }
    if ($bitmap) { $bitmap.Dispose() }
    if ($input) { $input.Dispose() }
    if ($stream) { $stream.Dispose() }
  }
}
