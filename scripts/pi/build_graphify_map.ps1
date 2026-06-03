# Build/refresh the Graphify map for the current repository.
# Requires: uv tool install graphifyy

$ErrorActionPreference = "Stop"

$graphify = Get-Command graphify -ErrorAction SilentlyContinue
if (-not $graphify) {
    Write-Host "graphify command not found. Install with: uv tool install graphifyy" -ForegroundColor Red
    exit 1
}

Write-Host "Building Graphify AST map for current repo..." -ForegroundColor Green
graphify update . --no-cluster

Write-Host "Building Graphify MCP search index..." -ForegroundColor Green
npx -y graphify-mcp-tools index --graph graphify-out

Write-Host "Precomputing Graphify outlines..." -ForegroundColor Green
npx -y graphify-mcp-tools outline --graph graphify-out

Write-Host "Graphify local map ready at graphify-out/" -ForegroundColor Green
