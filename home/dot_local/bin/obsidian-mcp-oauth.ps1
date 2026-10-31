# GitHub OAuth Appの秘密情報をSSHの標準入力で送り、ラズパイに暗号化保存する。
$ErrorActionPreference = 'Stop'
$sshExe = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
$secret = Read-Host 'GitHub OAuth AppのClient Secret（画面には表示しません）' -AsSecureString
if ($secret.Length -eq 0) { throw 'Client Secretが空です。変更しませんでした。' }
$process = New-Object System.Diagnostics.Process
$process.StartInfo.FileName = $sshExe
$process.StartInfo.Arguments = '-o BatchMode=yes -o ConnectTimeout=15 raspi4 "umask 077; mkdir -p ~/.local/share/obsidian-mcp/credentials && systemd-creds encrypt --user --with-key=host --name=github-client-secret - ~/.local/share/obsidian-mcp/credentials/github-client-secret.cred.tmp && mv ~/.local/share/obsidian-mcp/credentials/github-client-secret.cred.tmp ~/.local/share/obsidian-mcp/credentials/github-client-secret.cred"'
$process.StartInfo.UseShellExecute = $false
$process.StartInfo.CreateNoWindow = $true
$process.StartInfo.RedirectStandardInput = $true
$process.StartInfo.RedirectStandardOutput = $true
$process.StartInfo.RedirectStandardError = $true
$pointer = [IntPtr]::Zero
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    if (-not $process.Start()) { throw 'SSHを起動できませんでした。' }
    $process.StandardInput.Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer))
    $process.StandardInput.Close()
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    $errorTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(60000)) {
        $process.Kill()
        throw 'SSHが時間内に終了しませんでした。再実行してください。'
    }
    $null = $outputTask.Result
    $null = $errorTask.Result
    if ($process.ExitCode -ne 0) { throw '暗号化保存に失敗しました。SSH接続とsystemd-credsを確認してください。' }
    Write-Host 'Client Secretをラズパイへ暗号化保存しました。'
} finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $secret.Dispose()
    $process.Dispose()
}
