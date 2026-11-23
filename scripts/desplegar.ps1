# =============================================================================
# desplegar.ps1 - Despliegue MANUAL equivalente al job "desplegar" del CD (plan B)
# =============================================================================
# Úsalo solo si tu tenant de Azure for Students no permite crear la identidad de GitHub Actions
# (az ad sp create-for-rbac). Hace lo mismo que el CD: aplica despliegue/containerapp.yaml con la
# imagen del commit actual de main, corre la prueba de humo y hace rollback si falla.
#   .\scripts\desplegar.ps1
param(
    [string]$Grupo = "rg-wodpredict-fase3",
    [string]$App = "wodpredict-api",
    [string]$Repo = "ghcr.io/rick-lastra/wodpredict-ai_etapa-7_pipeline-mlops"
)
$ErrorActionPreference = "Stop"
$Commit = (git rev-parse HEAD).Trim()
$Imagen = "${Repo}:sha-$($Commit.Substring(0,7))"
$Version = (Get-Content modelo/metadata.json -Raw | ConvertFrom-Json).version
$Previa = az containerapp show -n $App -g $Grupo --query "properties.template.containers[0].image" -o tsv
Write-Host "Desplegando $Imagen (modelo v$Version). Imagen anterior: $Previa"

$yaml = (Get-Content despliegue/containerapp.yaml -Raw).Replace('${IMAGEN}', $Imagen).Replace('${GIT_COMMIT}', $Commit)
$tmp = Join-Path $env:TEMP "containerapp.yaml"
Set-Content -Path $tmp -Value $yaml -Encoding utf8
az containerapp update -n $App -g $Grupo --yaml $tmp -o none

$Url = "https://" + (az containerapp show -n $App -g $Grupo --query properties.configuration.ingress.fqdn -o tsv)
python scripts/smoke_test.py $Url --version-esperada $Version --repeticiones 20
if ($LASTEXITCODE -ne 0) {
    Write-Host "Prueba de humo FALLÓ: rollback a $Previa" -ForegroundColor Red
    az containerapp update -n $App -g $Grupo --image $Previa -o none
    exit 1
}
Write-Host "Despliegue correcto: $Url" -ForegroundColor Green
