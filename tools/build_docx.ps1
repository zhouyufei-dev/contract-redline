# One-off helper: package fake_contract_01.txt into a real .docx
# (so step 3's parser has a genuine Word file to read before python-docx exists).
# Not part of the application. Run once.

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root = Split-Path -Parent $PSScriptRoot
$txtPath = Join-Path $root 'data\samples\fake_contract_01.txt'
$docxPath = Join-Path $root 'data\samples\fake_contract_01.docx'

function Esc([string]$s) {
    $s.Replace('&', '&amp;').Replace('<', '&lt;').Replace('>', '&gt;')
}

$lines = Get-Content -LiteralPath $txtPath -Encoding UTF8

$sb = New-Object System.Text.StringBuilder
[void]$sb.Append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
[void]$sb.Append('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>')

foreach ($line in $lines) {
    if ([string]::IsNullOrWhiteSpace($line)) {
        [void]$sb.Append('<w:p><w:pPr><w:spacing w:after="0"/></w:pPr></w:p>')
    }
    else {
        [void]$sb.Append('<w:p><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr>')
        [void]$sb.Append('<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="22"/></w:rPr>')
        [void]$sb.Append('<w:t xml:space="preserve">' + (Esc $line) + '</w:t></w:r></w:p>')
    }
}

[void]$sb.Append('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>')
[void]$sb.Append('</w:body></w:document>')

$contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
'<Default Extension="xml" ContentType="application/xml"/>' +
'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
'</Types>'

$rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
'</Relationships>'

if (Test-Path -LiteralPath $docxPath) { Remove-Item -LiteralPath $docxPath -Force }

$enc = New-Object System.Text.UTF8Encoding($false)

function Add-Entry($zip, [string]$name, [string]$content) {
    $entry = $zip.CreateEntry($name, [System.IO.Compression.CompressionLevel]::Optimal)
    $stream = $entry.Open()
    $bytes = $enc.GetBytes($content)
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Dispose()
}

$zip = [System.IO.Compression.ZipFile]::Open($docxPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    Add-Entry $zip '[Content_Types].xml' $contentTypes
    Add-Entry $zip '_rels/.rels' $rels
    Add-Entry $zip 'word/document.xml' $sb.ToString()
}
finally {
    $zip.Dispose()
}

Write-Output "WROTE: $docxPath"
$zipCheck = [System.IO.Compression.ZipFile]::OpenRead($docxPath)
try {
    $zipCheck.Entries | ForEach-Object { "  entry: {0}  ({1} bytes)" -f $_.FullName, $_.Length }
}
finally {
    $zipCheck.Dispose()
}
