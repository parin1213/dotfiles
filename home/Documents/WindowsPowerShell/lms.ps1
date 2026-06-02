# LM Studio (lms) helpers. Lazily dot-sourced by the PowerShell profile on first lmsi/lmsq call.
# Depends on $script:Utf8NoBom defined in the profile scope.

$script:LmsCliPath = Join-Path $env:USERPROFILE ".lmstudio\bin\lms.exe"
$script:LmsDefaultModel = "qwen/qwen3.5-9b"
$script:LmsServerBaseUrl = "http://127.0.0.1:1234"

function Invoke-WithUtf8Console {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock
    )

    $previousInputEncoding = [Console]::InputEncoding
    $previousOutputEncoding = [Console]::OutputEncoding
    $previousPipelineEncoding = $global:OutputEncoding

    try {
        [Console]::InputEncoding = $script:Utf8NoBom
        [Console]::OutputEncoding = $script:Utf8NoBom
        $global:OutputEncoding = $script:Utf8NoBom
        & $ScriptBlock
    }
    finally {
        [Console]::InputEncoding = $previousInputEncoding
        [Console]::OutputEncoding = $previousOutputEncoding
        $global:OutputEncoding = $previousPipelineEncoding
    }
}

function ConvertTo-WindowsProcessArgument {
    param(
        [AllowEmptyString()]
        [string]$Argument
    )

    if ($null -eq $Argument -or $Argument.Length -eq 0) {
        return '""'
    }

    if ($Argument -notmatch '[\s"]') {
        return $Argument
    }

    $escaped = $Argument -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    '"' + $escaped + '"'
}

function Invoke-LmsCliQuiet {
    param(
        [string[]]$Arguments
    )

    $cli = Get-LmsCliCommand
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $cli
    $psi.Arguments = ($Arguments | ForEach-Object { ConvertTo-WindowsProcessArgument $_ }) -join ' '
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    try {
        $psi.StandardOutputEncoding = $script:Utf8NoBom
        $psi.StandardErrorEncoding = $script:Utf8NoBom
    }
    catch {
    }

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    $process.Start() | Out-Null

    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    $process.Dispose()

    if ($exitCode -ne 0) {
        if ($stderr) {
            throw $stderr.Trim()
        }

        if ($stdout) {
            throw $stdout.Trim()
        }

        throw "LM Studio CLI exited with code $exitCode."
    }

    [PSCustomObject]@{
        Stdout = $stdout.Trim()
        Stderr = $stderr.Trim()
    }
}

function Test-LmsServerAvailable {
    try {
        $null = Invoke-RestMethod -Method Get -Uri ($script:LmsServerBaseUrl + "/api/v1/models") -TimeoutSec 2
        $true
    }
    catch {
        $false
    }
}

function Start-LmsServerIfNeeded {
    if (Test-LmsServerAvailable) {
        return
    }

    Invoke-LmsCliQuiet @('server', 'start') | Out-Null

    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 250
        if (Test-LmsServerAvailable) {
            return
        }
    }

    throw "LM Studio API server did not become available at $script:LmsServerBaseUrl."
}

function Get-LmsModelCatalog {
    Start-LmsServerIfNeeded
    $response = Invoke-RestMethod -Method Get -Uri ($script:LmsServerBaseUrl + "/api/v1/models") -TimeoutSec 10
    if ($response.models) {
        return $response.models
    }

    @()
}

function Get-LmsLoadedInstanceId {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Model
    )

    $modelEntry = Get-LmsModelCatalog | Where-Object { $_.key -eq $Model } | Select-Object -First 1
    if ($null -eq $modelEntry) {
        return $null
    }

    if ($modelEntry.loaded_instances -and $modelEntry.loaded_instances.Count -gt 0) {
        return $modelEntry.loaded_instances[0].id
    }

    $null
}

function Ensure-LmsModelLoaded {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Model,
        [int]$Ttl = 600
    )

    Start-LmsServerIfNeeded

    $instanceId = Get-LmsLoadedInstanceId -Model $Model
    if ($instanceId) {
        return $instanceId
    }

    Invoke-LmsCliQuiet @('load', $Model, '--ttl', $Ttl.ToString(), '-y') | Out-Null

    $instanceId = Get-LmsLoadedInstanceId -Model $Model
    if ($instanceId) {
        return $instanceId
    }

    throw "LM Studio loaded '$Model', but no active instance was reported by the API."
}

function Write-LmsVisibleText {
    param(
        [string]$Text,
        [hashtable]$State
    )

    if ([string]::IsNullOrEmpty($Text)) {
        return
    }

    if (-not $State.HasEmittedVisibleText) {
        $Text = $Text.TrimStart("`r", "`n")
    }

    if ([string]::IsNullOrEmpty($Text)) {
        return
    }

    $State.HasEmittedVisibleText = $true
    [void]$State.OutputBuilder.Append($Text)
    [Console]::Write($Text)
}

function Handle-LmsStreamEvent {
    param(
        [string]$EventName,
        [string]$EventData,
        [hashtable]$State
    )

    if ([string]::IsNullOrWhiteSpace($EventName)) {
        return
    }

    if ($EventName -eq "message.delta") {
        $payload = $EventData | ConvertFrom-Json
        Write-LmsVisibleText -Text $payload.content -State $State
        return
    }

    if ($EventName -eq "reasoning.delta") {
        if (-not $State.ShowThinking) {
            return
        }

        if (-not $State.ReasoningOpen) {
            Write-LmsVisibleText -Text "<think>`n" -State $State
            $State.ReasoningOpen = $true
        }

        $payload = $EventData | ConvertFrom-Json
        Write-LmsVisibleText -Text $payload.content -State $State
        return
    }

    if ($EventName -eq "reasoning.end") {
        if ($State.ShowThinking -and $State.ReasoningOpen) {
            Write-LmsVisibleText -Text "`n</think>`n`n" -State $State
            $State.ReasoningOpen = $false
        }
        return
    }

    if ($EventName -eq "error") {
        $payload = $EventData | ConvertFrom-Json
        if ($payload.error.message) {
            throw $payload.error.message
        }

        throw "LM Studio API returned an error event."
    }
}

function Invoke-LmsApiPromptStreaming {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Model,
        [Parameter(Mandatory = $true)]
        [string]$Prompt,
        [ValidateSet("think", "no_think", "auto")]
        [string]$Thinking = "think",
        [switch]$ShowThinking,
        [int]$Ttl = 600
    )

    $modelReference = Ensure-LmsModelLoaded -Model $Model -Ttl $Ttl
    $state = @{
        ShowThinking = $ShowThinking.IsPresent
        ReasoningOpen = $false
        HasEmittedVisibleText = $false
        OutputBuilder = (New-Object System.Text.StringBuilder)
    }

    $body = [ordered]@{
        model = $modelReference
        input = $Prompt
        stream = $true
        store = $false
    }

    switch ($Thinking) {
        "think" {
            $body.reasoning = "on"
        }
        "no_think" {
            $body.reasoning = "off"
        }
    }

    $bodyJson = $body | ConvertTo-Json -Depth 8 -Compress
    $bodyBytes = $script:Utf8NoBom.GetBytes($bodyJson)

    $request = [System.Net.HttpWebRequest]::Create($script:LmsServerBaseUrl + "/api/v1/chat")
    $request.Method = "POST"
    $request.ContentType = "application/json"
    $request.Accept = "text/event-stream"
    $request.Timeout = 600000
    $request.ReadWriteTimeout = 600000
    $request.KeepAlive = $true
    $request.ContentLength = $bodyBytes.Length

    $requestStream = $request.GetRequestStream()
    try {
        $requestStream.Write($bodyBytes, 0, $bodyBytes.Length)
    }
    finally {
        $requestStream.Dispose()
    }

    try {
        $response = $request.GetResponse()
    }
    catch [System.Net.WebException] {
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream(), $script:Utf8NoBom)
            try {
                $message = $reader.ReadToEnd().Trim()
            }
            finally {
                $reader.Dispose()
                $_.Exception.Response.Dispose()
            }

            if ($message) {
                throw $message
            }
        }

        throw
    }

    $reader = New-Object System.IO.StreamReader($response.GetResponseStream(), $script:Utf8NoBom)
    $eventName = $null
    $dataLines = New-Object System.Collections.Generic.List[string]

    try {
        while (($line = $reader.ReadLine()) -ne $null) {
            if ($line.Length -eq 0) {
                if ($eventName) {
                    Handle-LmsStreamEvent -EventName $eventName -EventData ($dataLines -join "`n") -State $state
                }

                $eventName = $null
                $dataLines.Clear()
                continue
            }

            if ($line.StartsWith("event:")) {
                $eventName = $line.Substring(6).Trim()
                continue
            }

            if ($line.StartsWith("data:")) {
                $dataLines.Add($line.Substring(5).TrimStart())
            }
        }

        if ($eventName) {
            Handle-LmsStreamEvent -EventName $eventName -EventData ($dataLines -join "`n") -State $state
        }
    }
    finally {
        $reader.Dispose()
        $response.Dispose()
    }

    if ($state.ShowThinking -and $state.ReasoningOpen) {
        Write-LmsVisibleText -Text "`n</think>`n`n" -State $state
        $state.ReasoningOpen = $false
    }

    if ($state.OutputBuilder.Length -gt 0) {
        $lastChar = $state.OutputBuilder.ToString($state.OutputBuilder.Length - 1, 1)
        if ($lastChar -ne "`n") {
            [Console]::WriteLine()
        }
    }

    $state.OutputBuilder.ToString()
}

function Get-LmsCliCommand {
    $command = Get-Command lms -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    if (Test-Path $script:LmsCliPath) {
        return $script:LmsCliPath
    }

    throw "LM Studio CLI (lms) was not found."
}

function Get-LmsDefaultModel {
    $script:LmsDefaultModel
}

function Set-LmsDefaultModel {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Model
    )

    $script:LmsDefaultModel = $Model
    $script:LmsDefaultModel
}

function lmsi {
    param(
        [string]$Model = $script:LmsDefaultModel,
        [int]$Ttl = 600
    )

    $cli = Get-LmsCliCommand
    Invoke-WithUtf8Console {
        & $cli chat $Model --ttl $Ttl
    }
}

function lmsq {
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Prompt,
        [string]$Model = $script:LmsDefaultModel,
        [ValidateSet("think", "no_think", "auto")]
        [string]$Thinking = "think",
        [switch]$ShowThinking,
        [int]$Ttl = 600,
        [switch]$PassThru
    )

    $text = Invoke-WithUtf8Console {
        Invoke-LmsApiPromptStreaming -Model $Model -Prompt $Prompt.Trim() -Thinking $Thinking -ShowThinking:$ShowThinking -Ttl $Ttl
    }

    if ($PassThru) {
        $text
    }
}