# -*- coding: utf-8 -*-

from __future__ import print_function

try:
    from itertools import izip as zip  # PY2
except ImportError:
    pass  # PY3

from ..util import load_module, random_wait
from ..util import classlogger

from ..actions import action

from slipstream.api import SlipStreamError

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
    'softlayer': 'slipstream_nativesoftlayer.NativeSoftLayerClientCloud'
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
@action('start-deployment')
class DeploymentStartJob(object):
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

    def _get_deployment(self):
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
    def deployment(self):
        if self._deployment is None:
            self._deployment = self._get_deployment()
        return self._deployment

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

    @staticmethod
    def dict2tuple(d, *keys):
        return tuple([d[k] for k in keys])

    @classmethod
    def combine_acl_rules(cls, *rules_args):
        rule_attrs = ('type', 'principal', 'right')
        rules_set = {cls.dict2tuple(r, *rule_attrs) for rules in rules_args for r in rules}
        return [dict(zip(rule_attrs, r)) for r in rules_set]

    def get_cloud_credentials(self, credentials_ids):
        cimi_filter = ' or '.join(['id="{}"'.format(id) for id in credentials_ids])
        cimi_filter = 'type^="cloud-cred-" and ({})'.format(cimi_filter)
        cimi_response = self.ss_api.cimi_search('credentials', filter=cimi_filter)
        return [credential.json for credential in cimi_response.resources()]

    def acl_rules_from_managers(self, extra_cloud_credentials=None):
        rules = []

        cloud_credentials = [self.cloud_credential]
        if extra_cloud_credentials:
            cloud_credentials += extra_cloud_credentials

        for cloud_credential in cloud_credentials:
            managers = cloud_credential.get('managers', [])
            for manager in managers:
                rules.append(dict(right='VIEW', **manager))

        return rules

    def create_vm(self, vm_id, vm):
        cimi_new_vm = self._create_cimi_vm(vm_id, vm)

        cimi_new_vm['acl']['rules'] = self.combine_acl_rules(cimi_new_vm['acl']['rules'],
                                                             self.acl_rules_from_managers())

        try:
            cimi_vm_id = self.ss_api.cimi_add('virtualMachines', cimi_new_vm).json.get('resource-id')
            self.logger.info('Added new VM: {}.'.format(cimi_vm_id))
        except SlipStreamError as e:
            if e.response.status_code == 409:
                cimi_vm_id = e.response.json()['resource-id']
                # Could happen when VM is beeing created at same time by different thread
                self.logger.info('VM creation issue due to duplication of {}.'.format(cimi_vm_id))
                self.update_vm(vm_id, self._get_existing_virtual_machine(vm_id), vm)
            else:
                raise e
        return cimi_vm_id

    def update_vm(self, vm_id, existing_vms, vm):
        existing_vm = existing_vms.resources_list[0].json
        cimi_vm_id = existing_vm['id']
        credentials = existing_vm['credentials'][:]

        cimi_vm = self._create_cimi_vm(vm_id, vm)

        cimi_cloud_credentials = self.get_cloud_credentials([c['href'] for c in credentials])

        cimi_vm['acl']['rules'] = self.combine_acl_rules(cimi_vm['acl']['rules'],
                                                         self.acl_rules_from_managers(cimi_cloud_credentials))

        # Remove credentials that doesn't exist anymore
        new_credentials = [{'href': c['id']} for c in cimi_cloud_credentials]

        if not self.cred_exist_already(existing_vm):
            self.logger.debug('Credential {} will be append to existing VM {}.'.format(self.cloud_credential['id'],
                                                                                       cimi_vm_id))
            new_credentials.append({'href': self.cloud_credential['id']})

        cimi_vm['credentials'] = new_credentials

        self.logger.info('Update existing VM: {}.'.format(cimi_vm_id))
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

    def handle_deployment(self):

        # get the cloud connector instance
        cloud_credential_id = 'credential/abcde'
        cloud_credential = self.ss_api.cimi_get(cloud_credential_id).json
        cloud_name = cloud_credential['connector']['href']
        cloud_configuration = self.ss_api.cimi_get(cloud_name).json
        connector_name = cloud_configuration['cloudServiceType']
        connector = load_module(connector_classes[connector_name])

        if not hasattr(connector, 'instantiate_from_cimi'):
            raise NotImplementedError('The connector "{}" is not compatible with the start_deployment job'
                                      .format(connector_name))
        connector_instance = self.connector.instantiate_from_cimi(cloud_configuration, cloud_credential)

        # get module
        module = self.deployment['module']

        # start on cloud
        connector_instance.start(module)

        return 3


    def start_deployment(self):
        self.logger.info('Deployment start job started for {}.'.format(self.deployment['id']))

        self.job.set_progress(10)

        self.handle_deployment()

        return 10000

    def do_work(self):
        self.start_deployment()
