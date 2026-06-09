param environmentName string
param location string

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'pg-${environmentName}'
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: 'continuum'
    administratorLoginPassword: 'ChangeMe-${uniqueString(resourceGroup().id)}!'
    storage: { storageSizeGB: 32 }
    highAvailability: { mode: 'Disabled' }
  }
}

resource db 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: pg
  name: 'continuum'
}

output host string = pg.properties.fullyQualifiedDomainName
