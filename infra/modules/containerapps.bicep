param environmentName string
param location string
param managedIdentityId string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${environmentName}'
  location: location
  properties: {}
}

// Placeholder apps; azd injects the built images on `azd up`.
output environmentId string = env.id
output managedIdentityId string = managedIdentityId
