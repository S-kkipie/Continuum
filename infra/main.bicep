targetScope = 'resourceGroup'

@minLength(3)
param environmentName string
param location string = resourceGroup().location

module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: { environmentName: environmentName, location: location }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: { environmentName: environmentName, location: location }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: { environmentName: environmentName, location: location }
}

module search 'modules/search.bicep' = {
  name: 'search'
  params: { environmentName: environmentName, location: location }
}

module apps 'modules/containerapps.bicep' = {
  name: 'containerapps'
  params: {
    environmentName: environmentName
    location: location
    managedIdentityId: identity.outputs.identityId
  }
}

output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_STORAGE_ACCOUNT string = storage.outputs.accountName
output POSTGRES_HOST string = postgres.outputs.host
