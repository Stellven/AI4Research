# Pester 5 tests for the read-only Windows/WSL evidence doctor. Native WSL
# commands are mocked so failures cannot be mistaken for evidence and stale
# port markers cannot be reported as a running Solar status server.

BeforeAll {
    . "$PSScriptRoot/../scripts/windows-evidence-doctor.ps1"
}

Describe 'Windows evidence doctor WSL truthfulness' {
    AfterEach { $global:LASTEXITCODE = 0 }

    It 'discards stdout when wsl.exe exits nonzero' {
        Mock wsl.exe {
            $global:LASTEXITCODE = 1
            'misleading stale output'
        }
        (Invoke-WslText 'whoami' 'Ubuntu-24.04') | Should -Be ''
    }

    It 'filters Docker Desktop internal distros from automatic selection' {
        Mock Get-RegisteredDistro { @('docker-desktop', 'docker-desktop-data', 'Debian') }
        Resolve-Distro | Should -Be 'Debian'
    }

    It 'marks a numeric but unhealthy port marker as stale' {
        Mock Invoke-WslText {
            param([string]$cmd, [string]$distro)
            if ($cmd -like 'cat *status-server.port*') { return '8765' }
            if ($cmd -like 'curl *healthz*') { return 'fail' }
            return ''
        }
        $state = Get-WslStatusServerEvidence 'Ubuntu-24.04'
        $state.PortNumber | Should -Be ''
        $state.StatusServerPort | Should -Match 'stale'
        $state.WslToLoopback | Should -Be 'fail'
    }

    It 'accepts a numeric port only after in-WSL health succeeds' {
        Mock Invoke-WslText {
            param([string]$cmd, [string]$distro)
            if ($cmd -like 'cat *status-server.port*') { return '8765' }
            if ($cmd -like 'curl *healthz*') { return 'ok' }
            return ''
        }
        $state = Get-WslStatusServerEvidence 'Ubuntu-24.04'
        $state.PortNumber | Should -Be '8765'
        $state.StatusServerPort | Should -Be '8765'
        $state.WslToLoopback | Should -Be 'ok'
    }
}
