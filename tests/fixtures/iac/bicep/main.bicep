// Portail de rendez-vous (gabarit de test)
param prefix string = 'rdv'

resource vnet 'Microsoft.Network/virtualNetworks@2023-04-01' = {
  name: 'vnet-rdv'
  location: 'francecentral'
  properties: {
    addressSpace: { addressPrefixes: ['10.1.0.0/16'] }
  }
}

resource appSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-04-01' = {
  parent: vnet
  name: 'snet-app'
  properties: { addressPrefix: '10.1.1.0/24' }
}

resource plan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: 'plan-rdv'
  location: 'francecentral'
  sku: { name: 'P1v3' }
}

resource web 'Microsoft.Web/sites@2022-09-01' = {
  name: 'app-rdv'
  location: 'francecentral'
  properties: {
    serverFarmId: plan.id
    virtualNetworkSubnetId: appSubnet.id
    siteConfig: {
      appSettings: [
        { name: 'DB_HOST', value: db.properties.fullyQualifiedDomainName }
        { name: 'VAULT', value: vault.properties.vaultUri }
      ]
    }
  }
}

resource jobs 'Microsoft.Web/sites@2022-09-01' = {
  name: 'func-rappels'
  location: 'francecentral'
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: plan.id
    siteConfig: {
      appSettings: [
        { name: 'BUS', value: bus.name }
        { name: 'DB_HOST', value: db.properties.fullyQualifiedDomainName }
      ]
    }
  }
}

resource db 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
  name: 'psql-rdv'
  location: 'francecentral'
}

resource bus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: 'sb-rdv'
  location: 'francecentral'
}

resource vault 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: 'kv-rdv'
  location: 'francecentral'
  properties: { tenantId: subscription().tenantId, sku: { family: 'A', name: 'standard' } }
}
