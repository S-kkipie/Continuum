param environmentName string
param location string

resource sa 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: toLower('st${environmentName}${uniqueString(resourceGroup().id)}')
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: { allowBlobPublicAccess: false }
}

output accountName string = sa.name
