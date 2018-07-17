# -*- coding: utf-8 -*-

from __future__ import print_function

from ..util import load_module, classlogger, random_wait

from ..actions import action

from slipstream.api import SlipStreamError

connector_classes = {
    'azure':                  'slipstream_azure.AzureClientCloud',
    'cloudstack':             'slipstream_cloudstack.CloudStackClientCloud',
    'cloudstackadvancedzone': 'slipstream_cloudstack.CloudStackAdvancedZoneClientCloud',
    'ec2':                    'slipstream_ec2.Ec2ClientCloud',
    'exoscale':               'slipstream_exoscale.ExoscaleClientCloud',
    'nuvlabox':               'slipstream_nuvlabox.NuvlaBoxClientCloud',
    'opennebula':             'slipstream_opennebula.OpenNebulaClientCloud',
    'openstack':              'slipstream_openstack.OpenStackClientCloud',
    'otc':                    'slipstream_otc.OpenTelekomClientCloud',
    'softlayer':              'slipstream_nativesoftlayer.NativeSoftLayerClientCloud'
}

limits_aggregation = {
    "max_instances": "count:id",
    "max_cpu": "sum:serviceOffer/resource:vcpu",
    "max_memory": "sum:serviceOffer/resource:ram",
    # "max_images",
    # "max_networks",
    # "max_secondary_storage",
    # "max_public_ips",
    # "max_vpc",
    # "max_projects",
    # "max_volumes",
    # "max_primary_storage",
    # "max_snapshots"
}

@classlogger
@action('collect_quotas')
class QuotasCollectJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.ss_api = executor.ss_api
        self.timeout = 60  # seconds job should terminate in maximum 60 seconds

        self._cloud_credential = None
        self._connector_instance = None
        self._cloud_configuration = None
        self._connector_name = None
        self._cloud_name = None

    def _get_existing_quota(self, limit):
        return self.ss_api.cimi_search('quotas', filter='selection="credentials/href=\'{}\'" and aggregation="{}"'
                                       .format(self.cloud_credential['id'], limits_aggregation[limit]))

    def _generate_rules(self):
        credential_acl = self.cloud_credential["acl"]
        non_admin_rules = []
        if credential_acl["owner"]["principal"].lower() != "admin":
            non_admin_rules.append({"principal" : credential_acl["owner"]["principal"],
                "right" : "VIEW",
                "type" : credential_acl["owner"]["type"]
            })
        
        for rule in credential_acl["rules"]:
            if rule["principal"].lower() != "admin" and rule not in non_admin_rules:
                non_admin_rules.append({"principal" : rule["principal"],
                    "right" : "VIEW",
                    "type" : rule["type"]
                })

        return non_admin_rules

    @property
    def cloud_credential(self):
        if self._cloud_credential is None:
            self._cloud_credential = self.ss_api.cimi_get(self.job['targetResource']['href']).json
        return self._cloud_credential

    @property
    def cloud_name(self):
        return self.cloud_credential['connector']['href']

    @property
    def connector_name(self):
        return self.cloud_configuration['cloudServiceType']

    @property
    def connector(self):
        return load_module(connector_classes[self.connector_name])
    
    @property
    def cloud_configuration(self):
        if self._cloud_configuration is None:
            self._cloud_configuration = self.ss_api.cimi_get(self.cloud_name).json
        return self._cloud_configuration

    @property
    def connector_instance(self):
        if self._connector_instance is None:
            if not hasattr(self.connector, 'instantiate_from_cimi'):
                raise NotImplementedError('The connector "{}" is not compatible with the collect_virtual_machines job'
                                          .format(self.connector_name))
            self._connector_instance = self.connector.instantiate_from_cimi(self.cloud_configuration,
                                                                            self.cloud_credential)
        return self._connector_instance

    def create_quota_resource(self, limit_type, limit_value):
        description = 'limits regarding {}, for credential {} in {}'\
                    .format(limit_type, self.cloud_credential["id"], self.cloud_name)
        name = '{} in {}'.format(limit_type, self.cloud_name)
        resource = "VirtualMachine"
        aggregation = limits_aggregation[limit_type]
        limit = limit_value
        selection = "credentials/href='{}'".format(self.cloud_credential["id"])

        acl = {'owner': {'type': 'ROLE', 'principal': 'ADMIN'}}
        rules = self._generate_rules()
        acl.update(rules)

        quota_resource = {'resourceURI': 'http://sixsq.com/slipstream/1/Quota',
                   'description': description,
                   'name': name,
                   'limit': limit,
                   'resource': resource,
                   'acl': acl,
                   'aggregation': aggregation,
                   'selection': selection
        }
        
        return quota_resource

    def create_quota(self, limit_type, limit_value):
        cimi_new_quota = self.create_quota_resource(limit_type, limit_type)
        try:
            cimi_quota_id = self.ss_api.cimi_add('quotas', cimi_new_quota).json.get('resource-id')
            self.logger.info('Added new quota: {}'.format(cimi_quota_id))
        except SlipStreamError as e:
            if e.response.status_code == 409:
                cimi_quota_id = e.response.json()['resource-id']
                self.logger.info('Quota %s creation issue due to %s' % (cimi_quota_id, e))
            else:
                raise e

        return cimi_quota_id

    def update_quota(self, limit_type, limit_value, existing_quota):
        cimi_quota_id = existing_quota.resources_list[0].json['id']
        cimi_quota_resource = self.create_quota_resource(limit_type, limit_value)
        # ACLs are always updated
    
        self.logger.info('Update existing quota: {}'.format(cimi_quota_id))
        try:
            self.ss_api.cimi_edit(cimi_quota_id, cimi_quota_resource)
        except SlipStreamError as e:
            if e.response.status_code == 409:
                # Could happen when quota is beeing updated at same time by different thread
                self.logger.info('Quota update conflict of {}.').format(cimi_quota_id)
                random_wait(0.5, 5.0)
                self.update_quota(limit_type, limit_value, self._get_existing_quota(limit_type))
                # retry recursion is stopped by the job executor after self.timeout

        return cimi_quota_id

    def handle_quota(self, limits):
        self.logger.debug('Extracting quotas from limits: {}'.format(limits))

        # Quota resource already exists?
        for limit, value in limits.iteritems():
            existing_quota_resource = self._get_existing_quota(limit)
            if existing_quota_resource.count == 0:  # quota doesn't exist, create it
                cimi_quota_id = self.create_quota(limit, value)
            else:  # quota already exists, update it
                cimi_quota_id = self.update_quota(limit, value, existing_quota_resource)

        self.job.add_affected_resource(cimi_quota_id)


    def get_quotas(self):
        self.logger.info('Collect quotas started for {}.'.format(self.cloud_credential['id']))
        limits = self.connector_instance.ex_limits()

        self.job.set_progress(50)
        self.handle_quota(limits)
        self.job.set_progress(80)

        return 10000


    def do_work(self):
        self.get_quotas()
