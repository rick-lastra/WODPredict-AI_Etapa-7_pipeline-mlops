# azure_apagar.ps1 - Elimina TODO lo creado en Azure para no consumir créditos de Azure for Students.
# Borra el grupo de recursos completo (Container App, entorno y Log Analytics). No se puede deshacer.
#   .\scripts\azure_apagar.ps1
param([string]$Grupo = "rg-wodpredict-fase3")
az group delete --name $Grupo --yes --no-wait
Write-Host "Eliminación de $Grupo en curso (tarda unos minutos)."
