# Despliegue en Azure Container Apps (paso a paso)

Este paso se hace **una sola vez**. Después, cada merge a `main` despliega solo.

## 0. Antes de empezar
- Azure CLI instalado (`az version`) y sesión iniciada: `az login` (suscripción Azure for Students).
- El repo ya está en GitHub y el workflow **CD** corrió al menos una vez (pestaña *Actions* > CD > *Run workflow*), así que existe la imagen `ghcr.io/rick-lastra/wodpredict-ai_etapa-7_pipeline-mlops:latest`.
- Un token clásico de GitHub con permiso `read:packages` (GitHub > Settings > Developer settings > Personal access tokens). Azure lo usa para descargar la imagen de GHCR.
  - Alternativa: en GitHub > Packages > la imagen > *Package settings* > *Change visibility* > Public. Así no hace falta el token.

## 1. Crear la infraestructura
```powershell
$env:GHCR_PAT = "<token>"
.\scripts\azure_configurar.ps1
```
Crea `rg-wodpredict-fase3` en México Central, el entorno de Container Apps (con Log Analytics) y la app `wodpredict-api`. Al final imprime:
- un JSON → GitHub > Settings > Secrets and variables > Actions > **New repository secret** `AZURE_CREDENTIALS`;
- tres variables → pestaña **Variables**: `AZURE_RESOURCE_GROUP`, `AZURE_CONTAINERAPP`, `API_URL`.

## 2. Proteger main
GitHub > Settings > Branches > *Add rule* para `main`: **Require a pull request before merging** y **Require status checks to pass** (marcar los tres jobs del CI). Así nada llega a producción sin pasar las pruebas y el quality gate.

## 3. Probar el ciclo completo
*Actions* > CD > *Run workflow*. Debe terminar con la prueba de humo en verde y el enlace al entorno `produccion`.

## Si `az ad sp create-for-rbac` falla
Algunos tenants universitarios no permiten crear identidades. En ese caso:
- el CD sigue publicando la imagen en GHCR en cada merge (CI/CD parcial);
- el despliegue lo haces tú con `.\scripts\desplegar.ps1`, que hace exactamente lo mismo que el job del CD (aplica `containerapp.yaml`, prueba de humo y rollback). Documenta esta limitación en el PDF como decisión.

## Costos y apagado
- Con 0 réplicas de noche y 0.25 vCPU de día, la Etapa 6 estimó ≈ USD 116 al año en producción; durante las pruebas el consumo es de centavos.
- Al terminar la evaluación: `.\scripts\azure_apagar.ps1` borra todo el grupo de recursos.

## Observabilidad en Azure
Cada consulta escribe una línea JSON en stdout (`request_id`, `latencia_ms`, `estado_http`, `version_modelo`). En el portal: Container App > *Logs*:
```kusto
ContainerAppConsoleLogs_CL
| where Log_s startswith "{\"evento\": \"consulta\""
| extend d = parse_json(Log_s)
| summarize p99 = percentile(todouble(d.latencia_ms), 99), consultas = count() by bin(TimeGenerated, 1h)
```

> Nota: los comandos de Azure y el YAML de `despliegue/` no se pudieron probar contra una suscripción real al preparar el repo; la imagen, la API, las pruebas y el pipeline sí se probaron en local. Si `az containerapp update --yaml` rechaza algún campo, el mensaje de error dice cuál.
