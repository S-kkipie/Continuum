param environmentName string
param location string
param principalId string

// Azure AI Search is the Foundry IQ backing resource (knowledge bases / agentic retrieval).
// TODO (deploy task): set disableLocalAuth: true once all access is via managed identity.
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: toLower('srch-${environmentName}-${uniqueString(resourceGroup().id)}')
  location: location
  sku: { name: 'basic' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    semanticSearch: 'free'
  }
}

resource indexDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, 'SearchIndexDataContributor')
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource serviceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, 'SearchServiceContributor')
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output endpoint string = 'https://${search.name}.search.windows.net'
