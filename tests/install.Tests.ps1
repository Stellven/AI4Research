# Pester 5 unit tests for install.ps1 (the Windows/WSL2 bootstrapper).
# Dot-sources install.ps1 (its main block is guarded, so only the functions load) and exercises the
# logic that is otherwise "owner-Phase-F only": distro resolution (W6), WSL readiness (W6), the
# forwarded-flags/components rules (W7/desktop set), and that a failed in-WSL install surfaces as a
# throw instead of false success (W5/W2).
#
#   pwsh -c "Invoke-Pester ./tests/install.Tests.ps1"   (Pester 5+)
# Native wsl.exe is mocked; the mock manages $global:LASTEXITCODE because install.ps1 checks it.

BeforeAll {
    . "$PSScriptRoot/../install.ps1"
}

Describe 'Get-ForwardString' {
    # Dot-source per-case with explicit -ForwardArgs: install.ps1's params land in the dot-source
    # scope, so re-sourcing here is the reliable way to drive Get-ForwardString's input under Pester.
    It 'adds the desktop component set, --yes, and --bootstrap-system-deps when none are given' {
        . "$PSScriptRoot/../install.ps1"
        $s = Get-ForwardString
        $s | Should -Match 'kernel,harness,status-daemon'
        $s | Should -Match ([regex]::Escape("'--yes'"))
        $s | Should -Match '--bootstrap-system-deps'
    }
    It 'respects a caller-provided --components (no status-daemon injection)' {
        . "$PSScriptRoot/../install.ps1" -ForwardArgs '--components', 'kernel,harness'
        (Get-ForwardString) | Should -Not -Match 'status-daemon'
    }
    It 'does not double-add --yes' {
        . "$PSScriptRoot/../install.ps1" -ForwardArgs '--yes'
        ([regex]::Matches((Get-ForwardString), '--yes')).Count | Should -Be 1
    }
    It 'preserves spaces and apostrophes as single bash arguments' {
        . "$PSScriptRoot/../install.ps1" -ForwardArgs '--solar-home', '/tmp/My Home', "O'Reilly"
        $s = Get-ForwardString
        $bashQuote = "'" + '"' + "'" + '"' + "'"
        $s | Should -Match ([regex]::Escape("'/tmp/My Home'"))
        $s | Should -Match ([regex]::Escape("'O${bashQuote}Reilly'"))
    }
}

Describe 'Self invocation persistence' {
    It 'round-trips custom parameters and forwarded arguments through EncodedCommand' {
        . "$PSScriptRoot/../install.ps1" `
            -Distro 'Ubuntu Custom' `
            -BootstrapUrl "https://example.invalid/get-solar.sh?owner=O'Reilly" `
            -RepoUrl 'https://example.invalid/My Repo.git' `
            -ForwardArgs '--solar-home', '/tmp/My Home'
        $encoded = New-SelfInvocationEncodedCommand 'C:\Program Files\OpenSolar\install.ps1'
        $decoded = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($encoded))
        $decoded | Should -Match ([regex]::Escape("-Distro 'Ubuntu Custom'"))
        $decoded | Should -Match ([regex]::Escape("-BootstrapUrl 'https://example.invalid/get-solar.sh?owner=O''Reilly'"))
        $decoded | Should -Match ([regex]::Escape("-RepoUrl 'https://example.invalid/My Repo.git'"))
        $decoded | Should -Match ([regex]::Escape("-ForwardArgs @('--solar-home','/tmp/My Home')"))
        $tokens = $null
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseInput($decoded, [ref]$tokens, [ref]$errors)
        $errors.Count | Should -Be 0
    }

    It 'uses the encoded self-invocation helper for elevation and reboot resume' {
        $source = Get-Content "$PSScriptRoot/../install.ps1" -Raw
        ([regex]::Matches($source, 'New-SelfInvocationEncodedCommand')).Count | Should -BeGreaterOrEqual 3
        $source | Should -Not -Match '\$argList = .*\+ \$ForwardArgs'
        $source | Should -Not -Match 'RunOnce.*Get-ForwardString'
    }
}

Describe 'Resolve-Distro (W6: consistent distro)' {
    # The requested distro is the param default (Ubuntu-24.04); each case varies only the mocked
    # registered-distro list.
    It 'returns the default when nothing is registered' {
        Mock Get-RegisteredDistro { @() }
        Resolve-Distro | Should -Be 'Ubuntu-24.04'
    }
    It 'keeps the requested distro when it is registered' {
        Mock Get-RegisteredDistro { @('Debian', 'Ubuntu-24.04') }
        Resolve-Distro | Should -Be 'Ubuntu-24.04'
    }
    It 'falls back to the first registered distro when the requested one is absent' {
        Mock Get-RegisteredDistro { @('Debian', 'Ubuntu-22.04') }
        Resolve-Distro | Should -Be 'Debian'
    }
    It 'skips Docker Desktop internal distros when choosing a fallback' {
        Mock Get-RegisteredDistro { @('docker-desktop', 'docker-desktop-data', 'Debian') }
        Resolve-Distro | Should -Be 'Debian'
    }
    It 'does not honor an explicit Docker Desktop internal distro target' {
        . "$PSScriptRoot/../install.ps1" -Distro 'docker-desktop'
        Mock Get-RegisteredDistro { @('docker-desktop', 'Ubuntu-24.04') }
        Resolve-Distro | Should -Be 'Ubuntu-24.04'
    }
}

Describe 'Test-WslReady (W6: status + a real distro)' {
    AfterEach { $global:LASTEXITCODE = 0 }  # don't let a mock's exit code leak into Pester (pester#1616)
    It 'is false when wsl --status fails' {
        Mock wsl.exe { $global:LASTEXITCODE = 1 }
        Test-WslReady | Should -BeFalse
    }
    It 'is false when status is ok but no distro is registered' {
        Mock wsl.exe { $global:LASTEXITCODE = 0 }
        Mock Get-RegisteredDistro { @() }
        Test-WslReady | Should -BeFalse
    }
    It 'is true when status is ok and a distro is registered' {
        Mock wsl.exe { $global:LASTEXITCODE = 0 }
        Mock Get-RegisteredDistro { @('Ubuntu-24.04') }
        Test-WslReady | Should -BeTrue
    }
}

Describe 'Invoke-LinuxInstaller (W5/W2: no false success)' {
    AfterEach { $global:LASTEXITCODE = 0 }
    It 'throws when the in-WSL install returns a non-zero exit code' {
        # Defaults: $Distro=Ubuntu-24.04, $ForwardArgs=@(); the bundled get-solar.sh sibling exists.
        # wslpath resolves; the actual install command fails.
        Mock wsl.exe {
            if ($args -contains 'wslpath') { $global:LASTEXITCODE = 0; '/mnt/c/x/get-solar.sh'; return }
            $global:LASTEXITCODE = 1
        }
        { Invoke-LinuxInstaller } | Should -Throw
    }
}
