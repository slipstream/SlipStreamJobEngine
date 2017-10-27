# -*- coding: utf-8 -*-

from __future__ import print_function

from ..util import load_module
from ..util import classlogger

from ..actions import action

connector_classes = {
    'azure': 'slipstream_azure.AzureClientCloud',
    'cloudstack': 'slipstream_cloudstack.CloudStackClientCloud',
    'cloudstackadvancedzone': 'slipstream_cloudstack.CloudStackAdvancedZoneClientCloud',
    'ec2': 'slipstream_ec2.Ec2ClientCloud',
    'exoscale': 'slipstream_exoscale.ExoscaleClientCloud',
    'nuvlabox': 'slipstream_nuvlabox.NuvlaBoxClientCloud',
    'opennebula': 'slipstream_opennebula.OpenNebulaClientCloud',
    'openstack': 'slipstream_openstack.OpenStackClientCloud',
    'otc': 'slipstream_otc.OpenTelekomClientCloud',
    'softlayer': 'slipstream_nativesoftlayer.NativeSoftLayerClientCloud',
    'stratuslab': 'slipstream_stratuslab.StratusLabClientCloud',
    'stratuslabiter': 'slipstream_stratuslab.StratusLabIterClientCloud',
}


@classlogger
@action('collect_virtual_machines')
class VirtualMachinesCollectJob(object):
    def __init__(self, job):
        self.job = job
        self.ss_api = job.ss_api

        self._cloud_name = None
        self._cloud_credential = None
        self._cloud_configuration = None
        self._connector_name = None
        self._existing_virtual_machines = None
        self._connector_instance = None

        self.handled_vms_instance_id = set([])

    def _get_cloud_credential(self):
        return self.ss_api.cimi_get(self.job['targetResource']['href']).json

    def _get_cloud_configuration(self):
        return self.ss_api.cimi_get(self.cloud_name).json

    def _get_exiting_virtual_machines(self):
        return self.ss_api.cimi_search('virtualMachines',
                                       filter='credentials/href="{}" and connector/href="{}"'
                                       .format(self.cloud_credential['id'], self.cloud_name)).resources_list

    @property
    def cloud_credential(self):
        if self._cloud_credential is None:
            self._cloud_credential = self._get_cloud_credential()
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
    def connector_instance(self):
        if self._connector_instance is None:
            if not hasattr(self.connector, 'instantiate_from_cimi'):
                raise NotImplementedError('The connector "{}" is not compatible with the collect_virtual_machines job'
                                          .format(self.connector_name))
            self._connector_instance = self.connector.instantiate_from_cimi(self.cloud_configuration,
                                                                            self.cloud_credential)
        return self._connector_instance

    @property
    def cloud_configuration(self):
        if self._cloud_configuration is None:
            self._cloud_configuration = self._get_cloud_configuration()
        return self._cloud_configuration

    @property
    def existing_virtual_machines(self):
        if self._existing_virtual_machines is None:
            vms = self._get_exiting_virtual_machines()
            self._existing_virtual_machines = {vm['instanceID']: vm for vm in vms}
        return self._existing_virtual_machines

    def collect_virtual_machines(self):
        vms = self.connector_instance.list_instances()
        if len(vms) > 0:
            map(self.handle_vm, vms)
        else:
            self.logger.info('No VMs to collect.')

        self.delete_gone_vms()

        return 10000

    def is_new_vm(self, vm_id):
        return not self.existing_virtual_machines.get(vm_id)

    def handle_vm(self, vm):
        self.logger.debug('Handle following vm: {}'.format(vm))

        vm_id = str(self.connector_instance._vm_get_id_from_list_instances(vm))

        if self.is_new_vm(vm_id):
            cimi_new_vm = self._create_cimi_vm(vm_id, vm)
            vm_cimi_id = self.ss_api.cimi_add('virtualMachines', cimi_new_vm).json.get('resource-id')
            self.logger.info('Added new VM: {}'.format(vm_cimi_id))
        else:  # staying vm
            cimi_vm_id = self.existing_virtual_machines[vm_id]['id']
            cimi_vm = self._create_cimi_vm(vm_id, vm)
            self.logger.info('Update existing VM: {}'.format(cimi_vm_id))
            # TODO update credentials
            # Do update
            self.ss_api.cimi_update(cimi_vm.get('id'), cimi_vm)

        self.handled_vms_instance_id.add(vm_id)

    def _create_cimi_vm(self, vm_id, vm):
        vm_ip = str(self.connector_instance._vm_get_ip_from_list_instances(vm))
        vm_state = str(self.connector_instance._vm_get_state(vm)) or 'Unknown'
        vm_cpu = int(self.connector_instance._vm_get_cpu(vm)) or None
        vm_ram = int(self.connector_instance._vm_get_ram(vm)) or None
        vm_disk = int(self.connector_instance._vm_get_root_disk(vm)) or None
        vm_instanceType = self.connector_instance._vm_get_instance_type(vm) or None
        run_href = ''  # TODO
        run_owner = ''  # TODO
        service_offer_id = ''  # TODO
        service_offer = self.ss_api.cimi_get(service_offer_id).json

        if not service_offer.get('id'):
            filter_string = 'resource:type="VM" and connector/href="{}"'.format(self.cloud_name)
            if vm_cpu:
                filter_string += ' and resource:vcpu={}'.format(vm_cpu)
            if vm_ram:
                filter_string += ' and resource:ram={}'.format(vm_ram)
            if vm_disk:
                filter_string += ' and resource:disk={}'.format(vm_disk)
            if vm_instanceType:
                filter_string += ' and resource:instanceType={}'.format(vm_instanceType)

            service_offers_found = self.ss_api.cimi_search('serviceOffers', filter=filter_string,
                                                           orderby='price:unitCost').resources_list
            if len(service_offers_found > 0):
                service_offer = service_offers_found[0]
            else:
                service_offer = {'id': 'service-offer/unknown'}

        cimi_vm = {'resourceURI': 'http://sixsq.com/slipstream/1/VirtualMachine',
                   'connector': {'href': self.cloud_name},
                   'instanceID': vm_id,
                   'state': vm_state,
                   'ip': vm_ip,
                   'deployment': {'href': run_href,
                                  'user': {'href': run_owner}},
                   'credentials': [{'href': self.cloud_credential['id']}],
                   'acl': {'owner': {'type': 'ROLE', 'principal': 'ADMIN'},
                           'rules': [{'principal': run_owner, 'right': 'VIEW', 'type': 'USER'},
                                     {'principal': 'ADMIN', 'right': 'ALL', 'type': 'ROLE'}]
                           },
                   'serviceOffer': {'href': service_offer.get('id'),
                                    'resource:vcpu': service_offer.get('resource:vcpu', vm_cpu),
                                    'resource:ram': service_offer.get('resource:ram', vm_ram),
                                    'resource:disk': service_offer.get('', vm_disk),
                                    'resource:instanceType': service_offer.get('', vm_instanceType),
                                    'price:unitCost': service_offer.get('price:unitCost', ''),
                                    'price:billingPeriodCode': service_offer.get('price:billingPeriodCode', ''),
                                    'price:freeUnits': service_offer.get('price:freeUnits', ''),
                                    'price:unitCode': service_offer.get('price:unitCode', ''),
                                    }
                   }
        return cimi_vm

    def delete_gone_vms(self):
        gone_vms_ids = set(self.existing_virtual_machines.keys()).difference(self.handled_vms_instance_id)

        for gone_vm_instance_id in gone_vms_ids:
            vm_cimi_id = self.existing_virtual_machines[gone_vm_instance_id]['id']
            self.logger.info('Deleting gone VM: {}'.format(vm_cimi_id))
            self.ss_api.cimi_delete(vm_cimi_id)

    def do_work(self):
        self.collect_virtual_machines()
