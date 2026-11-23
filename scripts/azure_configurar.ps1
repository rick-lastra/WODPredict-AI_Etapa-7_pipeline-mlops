# =============================================================================
# azure_configurar.ps1 - Configuración INICIAL de Azure (se corre UNA sola vez, en PowerShell)
# =============================================================================
# Crea el grupo de recursos, el entorno de Container Apps (con Log Analytics) y la Container App con
# la primera imagen publicada por el workflow CD en GitHub Container Registry. Al final crea la
# identidad que usa GitHub Actions para desplegar (AZURE_CREDENTIALS).
#
# Requisitos: Azure CLI (az), sesión iniciada con la suscripción Azure for Students y que el workflow
# CD ya haya publicado al menos una imagen (pestaña Actions > CD > "1 · Publicar imagen en GHCR").
#
# Uso (desde la raíz del repo):
#   $env:GHCR_PAT = "<token clásico de GitHub con permiso read:packages>"
#   .\scripts\azure_configurar.ps1
param(
    [string]$Grupo = "rg-wodpredict-fase3",
    [string]$Region = "mexicocentral",
    [string]$Entorno = "cae-wodpredict-fase3",
    [string]$App = "wodpredict-api",
    [string]$UsuarioGitHub = "rick-lastra",
    [string]$Imagen = "ghcr.io/rick-lastra/wodpredict-ai_etapa-7_pipeline-mlops:latest"
)
$ErrorActionPreference = "Stop"

Write-Host "1. Extensión y proveedores de Azure" -ForegroundColor Cyan
az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

Write-Host "2. Grupo de recursos y entorno de Container Apps (crea Log Analytics)" -ForegroundColor Cyan
az group create --name $Grupo --location $Region -o none
az containerapp env create --name $Entorno --resource-group $Grupo --location $Region -o none

Write-Host "3. Container App con la imagen de GHCR (0.25 vCPU / 0.5 GiB, 0 a 5 réplicas)" -ForegroundColor Cyan
if (-not $env:GHCR_PAT) { throw "Define `$env:GHCR_PAT con un token de GitHub (read:packages) o haz pública la imagen en GHCR." }
az containerapp create --name $App --resource-group $Grupo --environment $Entorno `
    --image $Imagen --target-port 8000 --ingress external `
    --registry-server ghcr.io --registry-username $UsuarioGitHub --registry-password $env:GHCR_PAT `
    --cpu 0.25 --memory 0.5Gi --min-replicas 0 --max-replicas 5 -o none
$Fqdn = az containerapp show --name $App --resource-group $Grupo --query properties.configuration.ingress.fqdn -o tsv
Write-Host "   API: https://$Fqdn  (formulario en /app, Swagger en /docs)" -ForegroundColor Green

Write-Host "4. Identidad para GitHub Actions (solo con permiso sobre ESTE grupo de recursos)" -ForegroundColor Cyan
$Sub = az account show --query id -o tsv
Write-Host "   Copia TODO el JSON siguiente en GitHub > Settings > Secrets and variables > Actions > New secret: AZURE_CREDENTIALS"
az ad sp create-for-rbac --name "sp-wodpredict-github" --role contributor `
    --scopes "/subscriptions/$Sub/resourceGroups/$Grupo" --json-auth

Write-Host "`n5. Variables de GitHub (Settings > Secrets and variables > Actions > Variables):" -ForegroundColor Cyan
Write-Host "   AZURE_RESOURCE_GROUP = $Grupo"
Write-Host "   AZURE_CONTAINERAPP   = $App"
Write-Host "   API_URL              = https://$Fqdn"
