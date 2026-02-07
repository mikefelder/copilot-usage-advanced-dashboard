param location string
param tags object
param abbrs object
param resourceToken string
param principalId string
param doRoleAssignments bool

@description('Type of the principal - User for human users, ServicePrincipal for apps/managed identities')
param principalType string = 'User'


// Container registry
module containerRegistry 'br/public:avm/res/container-registry/registry:0.1.1' = {
  name: 'registry'
  params: {
    name: '${abbrs.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
    publicNetworkAccess: 'Enabled'
    roleAssignments: doRoleAssignments ? [
      {
        principalId: principalId
        principalType: principalType
        roleDefinitionIdOrName: 'AcrPull'
      }
    ] : []
  }
}

output AZURE_CONTAINER_REGISTRY_LOGIN_SERVER string = containerRegistry.outputs.loginServer
output AZURE_RESOURCE_REGISTRY_ID string = containerRegistry.outputs.resourceId
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistry.outputs.name
