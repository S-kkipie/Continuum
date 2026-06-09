param environmentName string
param location string
param principalId string

resource sa 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: toLower('st${environmentName}${uniqueString(resourceGroup().id)}')
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: { allowBlobPublicAccess: false }
}

// Managed-identity-first: grant the workload identity blob data access (no keys).
resource blobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sa.id, principalId, 'StorageBlobDataContributor')
  scope: sa
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output accountName string = sa.name
