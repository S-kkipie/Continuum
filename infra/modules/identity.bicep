param environmentName string
param location string

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${environmentName}'
  location: location
}

output identityId string = uami.id
output principalId string = uami.properties.principalId
