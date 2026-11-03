# One-off verification: is fake_contract_01.docx a valid OOXML package?
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$path = Join-Path (Split-Path -Parent $PSScriptRoot) 'data\samples\fake_contract_01.docx'
$zip = [System.IO.Compression.ZipFile]::OpenRead($path)
$entry = $zip.Entries | Where-Object { $_.FullName -eq 'word/document.xml' }
$stream = $entry.Open()
$reader = New-Object System.IO.StreamReader($stream)
$raw = $reader.ReadToEnd()
$reader.Dispose()
$zip.Dispose()

$xml = New-Object System.Xml.XmlDocument
$xml.LoadXml($raw)
$ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
$ns.AddNamespace('w', 'http://schemas.openxmlformats.org/wordprocessingml/2006/main')
$paras = $xml.SelectNodes('//w:p', $ns)

Write-Output ('XML well-formed : yes')
Write-Output ('paragraphs      : ' + $paras.Count)
Write-Output ('has Net 60 head : ' + ($raw -match 'sixty \(60\) days'))
Write-Output ('has R05 revision: ' + ($raw -match 'unlimited revisions'))
Write-Output ('file size bytes : ' + (Get-Item -LiteralPath $path).Length)
