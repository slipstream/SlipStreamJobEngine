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

get_limits_for = [
    "max_instances",
    "max_cpu",
    "max_memory",
    # "max_images",
    # "max_networks",
    # "max_secondary_storage",
    # "max_public_ips",
    # "max_vpc",
    # "max_projects",
    # "max_volumes",
    # "max_primary_storage",
    # "max_snapshots"
]

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

    def handle_quota(self, limits, key):
        self.logger.debug('Getting quota for API key: {}'.format(key))

        # Quota resource already exists?
        
        quotas = {}
        for limit_type in get_limits_for:
            quotas[limit_type] = limits[limit_type]

        vm_id = str(self.connector_instance._vm_get_id_from_list_instances(vm))
        exiting_vms = self._get_existing_virtual_machine(vm_id)

        if exiting_vms.count == 0:  # new vm
            cimi_vm_id = self.create_vm(vm_id, vm)
        else:  # staying vm
            cimi_vm_id = self.update_vm(vm_id, exiting_vms, vm)

        self.job.add_affected_resource(cimi_vm_id)
        self.handled_vms_instance_id.add(vm_id)

    def get_quotas(self):
        self.logger.info('Collect virtual machines started for {}.'.format(self.cloud_credential['id']))
        limits = self.connector_instance.ex_limits()
        api_key = connector_instance.api_key

        self.job.set_progress(50)

        self.handle_quota(limits, api_key)


    def do_work(self):
        self.get_quotas()
