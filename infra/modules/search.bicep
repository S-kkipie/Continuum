param environmentName string
param location string

// Azure AI Search is the Foundry IQ backing resource (knowledge bases / agentic retrieval).
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

output endpoint string = 'https://${search.name}.search.windows.net'
