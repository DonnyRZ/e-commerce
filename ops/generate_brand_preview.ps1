param(
    [string]$MarkPath = (Join-Path $PSScriptRoot "..\frontend\public\brand\logo-mark.png"),
    [string]$OutputPath = (Join-Path $PSScriptRoot "..\frontend\public\brand\og-image.png")
)

Add-Type -AssemblyName System.Drawing

$width = 1200
$height = 630
$ivory = [System.Drawing.Color]::FromArgb(255, 253, 247, 233)
$green = [System.Drawing.Color]::FromArgb(255, 2, 66, 44)
$gold = [System.Drawing.Color]::FromArgb(255, 205, 155, 58)
$bitmap = New-Object System.Drawing.Bitmap($width, $height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$mark = $null
$markGraphics = $null
$borderPen = $null
$dividerPen = $null
$titlePen = $null
$titleFont = $null

try {
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.Clear($ivory)

    $rounded = New-Object System.Drawing.Drawing2D.GraphicsPath
    $rounded.AddArc(18, 18, 48, 48, 180, 90)
    $rounded.AddArc($width - 66, 18, 48, 48, 270, 90)
    $rounded.AddArc($width - 66, $height - 66, 48, 48, 0, 90)
    $rounded.AddArc(18, $height - 66, 48, 48, 90, 90)
    $rounded.CloseFigure()
    $borderPen = New-Object System.Drawing.Pen($gold, 3)
    $graphics.DrawPath($borderPen, $rounded)
    $rounded.Dispose()

    $dividerPen = New-Object System.Drawing.Pen($gold, 2)
    $graphics.DrawLine($dividerPen, 510, 130, 510, $height - 130)

    $mark = [System.Drawing.Image]::FromFile($MarkPath)
    $markGraphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $markGraphics.DrawImage($mark, (New-Object System.Drawing.Rectangle(92, 140, 350, 350)))

    $title = "MUSLIMAH CANTIK"
    $titleX = 565
    $maxTitleWidth = $width - $titleX - 72
    $titleSize = 58
    do {
        if ($titleFont) { $titleFont.Dispose() }
        $titleFont = New-Object System.Drawing.Font("Georgia", $titleSize, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $titleSize -= 2
        $measure = $graphics.MeasureString($title, $titleFont)
    } while ($measure.Width -gt $maxTitleWidth -and $titleSize -gt 36)

    $titleY = [math]::Round(($height - $measure.Height) / 2)
    $graphics.DrawString($title, $titleFont, (New-Object System.Drawing.SolidBrush($green)), $titleX, $titleY)
    $titlePen = New-Object System.Drawing.Pen($gold, 5)
    $graphics.DrawLine($titlePen, $titleX, $titleY - 24, $titleX + 116, $titleY - 24)
    $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    if ($titlePen) { $titlePen.Dispose() }
    if ($dividerPen) { $dividerPen.Dispose() }
    if ($borderPen) { $borderPen.Dispose() }
    if ($titleFont) { $titleFont.Dispose() }
    if ($markGraphics) { $markGraphics.Dispose() }
    if ($mark) { $mark.Dispose() }
    if ($graphics) { $graphics.Dispose() }
    if ($bitmap) { $bitmap.Dispose() }
}
