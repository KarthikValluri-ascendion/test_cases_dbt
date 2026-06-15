# One-command demo reset. Returns the project to the RED starting state
# (the fixture model `fct_high_value_orders` becomes untested again).
# Usage:  .\demo\reset.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python ttd.py demo-reset
}
finally {
    Pop-Location
}
