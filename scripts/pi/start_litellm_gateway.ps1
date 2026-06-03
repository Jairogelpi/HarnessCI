# Start the HarnessCI LiteLLM gateway.
# Requires environment variables:
#   KILO_API_KEY
#   LITELLM_MASTER_KEY
# Optional Langfuse variables:
#   LANGFUSE_PUBLIC_KEY
#   LANGFUSE_SECRET_KEY
#   LANGFUSE_HOST

$ErrorActionPreference = "Stop"

$missing = @()
foreach ($name in @("KILO_API_KEY", "LITELLM_MASTER_KEY")) {
    if (-not [Environment]::GetEnvironmentVariable($name)) {
        $missing += $name
    }
}

if ($missing.Count -gt 0) {
    Write-Host "Missing required environment variables:" -ForegroundColor Red
    foreach ($name in $missing) { Write-Host "  - $name" -ForegroundColor Red }
    Write-Host "See configs/litellm/env.example.txt" -ForegroundColor Yellow
    exit 1
}

$litellm = Get-Command litellm -ErrorAction SilentlyContinue
if (-not $litellm) {
    Write-Host "litellm command not found. Install with: uv tool install litellm" -ForegroundColor Red
    exit 1
}

$config = Join-Path (Get-Location) "configs/litellm/harnessci.yaml"
if (-not (Test-Path $config)) {
    Write-Host "LiteLLM config not found: $config" -ForegroundColor Red
    exit 1
}

Write-Host "Starting LiteLLM gateway on http://localhost:4000" -ForegroundColor Green
Write-Host "Config: $config"
litellm --config $config --port 4000
