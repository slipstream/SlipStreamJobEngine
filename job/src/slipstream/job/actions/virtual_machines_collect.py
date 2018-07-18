# -*- coding: utf-8 -*-

from __future__ import print_function

from ..util import load_module, random_wait
from ..util import classlogger

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


def remove_prefix(prefix, input_string):
    return input_string[len(prefix):] if input_string.startswith(prefix) else input_string


def try_extract_number(input):
    val = None
    try:
        val = int(float(input))
    finally:
        return val


@classlogger
@action('collect_virtual_machines')
class VirtualMachinesCollectJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.ss_api = executor.ss_api
        self.timeout = 60  # seconds job should terminate in maximum 60 seconds

        self._cloud_name = None
        self._cloud_credential = None
        self._cloud_configuration = None
        self._connector_name = None
        self._existing_virtual_machines_connector = None
        self._existing_virtual_machines_credential = None
        self._connector_instance = None

        self.handled_vms_instance_id = set([])

    def _get_cloud_credential(self):
        return self.ss_api.cimi_get(self.job['targetResource']['href']).json

    def _get_cloud_configuration(self):
        return self.ss_api.cimi_get(self.cloud_name).json

    def _get_exiting_virtual_machines_for_credential(self):
        return self.ss_api.cimi_search('virtualMachines', filter='credentials/href="{}" and connector/href="{}"'
                                       .format(self.cloud_credential['id'], self.cloud_name)).resources_list

    def _get_existing_virtual_machine(self, vm_id):
        return self.ss_api.cimi_search('virtualMachines', filter='connector/href="{}" and instanceID="{}"'
                                       .format(self.cloud_name, vm_id))

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
    def existing_virtual_machines_credential(self):
        if self._existing_virtual_machines_credential is None:
            vms = self._get_exiting_virtual_machines_for_credential()
            self._existing_virtual_machines_credential = {vm.json['instanceID']: vm.json for vm in vms}
        return self._existing_virtual_machines_credential

    def cred_exist_already(self, exiting_vm):
        for cred in exiting_vm['credentials']:
            if cred['href'] == self.cloud_credential['id']:
                return True
        return False

    def create_vm(self, vm_id, vm):
        cimi_new_vm = self._create_cimi_vm(vm_id, vm)
        try:
            cimi_vm_id = self.ss_api.cimi_add('virtualMachines', cimi_new_vm).json.get('resource-id')
            self.logger.info('Added new VM: {}'.format(cimi_vm_id))
        except SlipStreamError as e:
            if e.response.status_code == 409:
                cimi_vm_id = e.response.json()['resource-id']
                # Could happen when VM is beeing created at same time by different thread
                self.logger.info('VM creation issue due to duplication of {}.')
                self.update_vm(vm_id, self._get_existing_virtual_machine(vm_id), vm)
            else:
                raise e
        return cimi_vm_id

    def update_vm(self, vm_id, existing_vms, vm):
        existing_vm = existing_vms.resources_list[0].json
        cimi_vm_id = existing_vm['id']
        credentials = existing_vm['credentials'][:]

        cimi_vm = self._create_cimi_vm(vm_id, vm)

        if not self.cred_exist_already(existing_vm):
            self.logger.debug('Credential {} will be append to existing VM {}.'
                              .format(self.cloud_credential['id'], cimi_vm_id))
            credentials.append({'href': self.cloud_credential['id']})

        cimi_vm['credentials'] = credentials

        self.logger.info('Update existing VM: {}'.format(cimi_vm_id))
        try:
            self.ss_api.cimi_edit(cimi_vm_id, cimi_vm)
        except SlipStreamError as e:
            if e.response.status_code == 409:
                # Could happen when VM is beeing updated at same time by different thread
                self.logger.info('VM update conflict of {}.').format(cimi_vm_id)
                random_wait(0.5, 5.0)
                self.update_vm(vm_id, self._get_existing_virtual_machine(vm_id), vm)
                # retry recursion is stopped by the job executor after self.timeout
        return cimi_vm_id

    def handle_vm(self, vm):
        self.logger.debug('Handle following vm: {}'.format(vm))

        vm_id = str(self.connector_instance._vm_get_id_from_list_instances(vm))
        exiting_vms = self._get_existing_virtual_machine(vm_id)

        if exiting_vms.count == 0:  # new vm
            cimi_vm_id = self.create_vm(vm_id, vm)
        else:  # staying vm
            cimi_vm_id = self.update_vm(vm_id, exiting_vms, vm)

        self.job.add_affected_resource(cimi_vm_id)
        self.handled_vms_instance_id.add(vm_id)

    def _create_cimi_vm(self, vm_id, vm):
        vm_ip = self.connector_instance._vm_get_ip_from_list_instances(vm) or None
        vm_state = self.connector_instance._vm_get_state(vm) or 'Unknown'
        vm_cpu = try_extract_number(self.connector_instance._vm_get_cpu(vm))
        vm_ram = try_extract_number(self.connector_instance._vm_get_ram(vm))
        vm_disk = try_extract_number(self.connector_instance._vm_get_root_disk(vm))
        vm_instanceType = self.connector_instance._vm_get_instance_type(vm) or None

        cloud = remove_prefix('connector/', self.cloud_name)

        filter_str_vdm = 'instanceID="{}" and cloud="{}"'.format(vm_id, cloud)
        vm_deployment_mappings = self.ss_api.cimi_search(
            'virtualMachineMappings', filter=filter_str_vdm, first=0, last=1)
        self.logger.debug('Found \'{}\' virtualMachineMappings for following filter_string \'{}\'.'
                          .format(vm_deployment_mappings.count, filter_str_vdm))

        if vm_deployment_mappings.count > 0:
            vm_deployment_mapping = vm_deployment_mappings.resources_list[0].json
        else:
            vm_deployment_mapping = {}
        run_uuid = vm_deployment_mapping.get('runUUID')
        run_owner = vm_deployment_mapping.get('owner')

        service_offer_id = vm_deployment_mapping.get('serviceOffer', {}).get('href')
        service_offer = {}
        if service_offer_id:
            try:
                service_offer = self.ss_api.cimi_get(service_offer_id).json
            except SlipStreamError as e:
                self.logger.warning('Failed to get service offer {}: {}'.format(service_offer_id, str(e)))

        if not service_offer.get('id'):
            filter_str_so = 'resource:type="VM" and connector/href="{}"'.format(cloud)
            if vm_cpu:
                filter_str_so += ' and resource:vcpu={}'.format(vm_cpu)
            if vm_ram:
                filter_str_so += ' and resource:ram={}'.format(vm_ram)
            if vm_disk:
                filter_str_so += ' and resource:disk={}'.format(vm_disk)
            if vm_instanceType:
                filter_str_so += ' and resource:instanceType="{}"'.format(vm_instanceType)

            service_offers_found = self.ss_api.cimi_search('serviceOffers', filter=filter_str_so,
                                                           orderby='price:unitCost', first=0, last=1)
            self.logger.debug('Found \'{}\' service offers for following filter_string \'{}\'.'
                              .format(service_offers_found.count, filter_str_so))
            if service_offers_found.count > 0:
                service_offer = service_offers_found.resources_list[0].json
            else:
                service_offer = {'id': 'service-offer/unknown'}

        cimi_vm = {'resourceURI': 'http://sixsq.com/slipstream/1/VirtualMachine',
                   'connector': {'href': self.cloud_name},
                   'instanceID': vm_id,
                   'state': vm_state,
                   'credentials': [{'href': self.cloud_credential['id']}],
                   'acl': {'owner': {'type': 'ROLE', 'principal': 'ADMIN'}},
                   'serviceOffer': {'href': service_offer.get('id'),
                                    'resource:vcpu': service_offer.get('resource:vcpu', vm_cpu),
                                    'resource:ram': service_offer.get('resource:ram', vm_ram),
                                    'resource:disk': service_offer.get('', vm_disk),
                                    'resource:instanceType': service_offer.get('', vm_instanceType),
                                    'price:unitCost': service_offer.get('price:unitCost', None),
                                    'price:billingPeriodCode': service_offer.get('price:billingPeriodCode', None),
                                    'price:freeUnits': service_offer.get('price:freeUnits', None),
                                    'price:unitCode': service_offer.get('price:unitCode', None)}}
        acl_rules = [{'principal': 'ADMIN', 'right': 'ALL', 'type': 'ROLE'},
                     {'principal': self.cloud_credential['acl']['owner']['principal'], 'right': 'VIEW',
                      'type': self.cloud_credential['acl']['owner']['type']}]

        deployment = {}
        if run_uuid:
            deployment = {'href': 'run/{}'.format(run_uuid)}
        if run_owner:
            deployment['user'] = {'href': 'user/{}'.format(run_owner)}
            acl_rules.append({'principal': run_owner, 'right': 'VIEW', 'type': 'USER'})

        if deployment:
            cimi_vm['deployment'] = deployment

        if vm_ip:
            cimi_vm['ip'] = vm_ip
        cimi_vm['acl']['rules'] = acl_rules
        return cimi_vm

    def delete_gone_vms(self):
        gone_vms_ids = set(self.existing_virtual_machines_credential.keys()).difference(self.handled_vms_instance_id)

        for gone_vm_instance_id in gone_vms_ids:
            vm_cimi_id = self.existing_virtual_machines_credential[gone_vm_instance_id]['id']
            self.logger.info('Deleting gone VM: {}'.format(vm_cimi_id))
            self.ss_api.cimi_delete(vm_cimi_id)

    def collect_virtual_machines(self):
        self.logger.info('Collect virtual machines started for {}.'.format(self.cloud_credential['id']))
        vms = self.connector_instance.list_instances()

        self.job.set_progress(40)

        if len(vms) > 0:
            map(self.handle_vm, vms)
        else:
            self.logger.info('No VMs to collect.')

        self.job.set_progress(80)

        self.delete_gone_vms()

        return 10000

    def do_work(self):
        self.collect_virtual_machines()
