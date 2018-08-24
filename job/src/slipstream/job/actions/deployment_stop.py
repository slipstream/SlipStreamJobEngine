# -*- coding: utf-8 -*-

from __future__ import print_function

try:
    from itertools import izip as zip  # PY2
except ImportError:
    pass  # PY3

from ..util import load_module
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


@action('stop_deployment')
class DeploymentStopJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.ss_api = executor.ss_api
        self.logger = job.logger
        self.timeout = 90  # seconds job should terminate in maximum 90 seconds

        self._deployment = None
        self._cloud_name = None
        self._cloud_credential = None
        self._cloud_configuration = None
        self._slipstream_configuration = None
        self._user = None
        self._connector_name = None
        self._connector_instance = None

        self.handled_vms_instance_id = set([])

    def _get_deployment(self):
        return self.ss_api.cimi_get(self.job['targetResource']['href']).json

    def _get_slipstream_configuration(self):
        return self.ss_api.cimi_get('configuration/slipstream').json

    @property
    def cloud_credential(self):
        if self._cloud_credential is None:
            self._cloud_credential = self.ss_api.cimi_get('credential/6d9aab4d-63b2-42ef-a633-bbb8faef8027').json
        return self._cloud_credential

    @property
    def deployment(self):
        if self._deployment is None:
            self._deployment = self._get_deployment()
        return self._deployment

    @property
    def connector(self):
        return load_module(connector_classes[self.connector_name])

    @staticmethod
    def connector_instance_userinfo(cloud_configuration, cloud_credential):
        connector_name = cloud_configuration['cloudServiceType']
        connector = load_module(connector_classes[connector_name])
        if not hasattr(connector, 'instantiate_from_cimi'):
            raise NotImplementedError('The connector "{}" is not compatible with the start_deployment job'
                                      .format(cloud_configuration['cloudServiceType']))
        return connector.instantiate_from_cimi(cloud_configuration, cloud_credential), \
               connector.get_user_info_from_cimi(cloud_configuration, cloud_credential)

    def handle_deployment(self):

        cloud_credential_id = 'credential/ecab1faf-32f6-4a76-8c2b-f93df4c4f75c'
        cloud_credential = self.ss_api.cimi_get(cloud_credential_id).json
        cloud_name = cloud_credential['connector']['href']
        cloud_configuration = self.ss_api.cimi_get(cloud_name).json
        connector_instance, user_info = \
            DeploymentStopJob.connector_instance_userinfo(cloud_configuration, cloud_credential)

        filter_param_instanceid = 'deployment/href="{}" and name="instanceid"'.format(self.deployment['id'])
        nodes_ids_resp = self.ss_api.cimi_search('deploymentParameters', filter=filter_param_instanceid,
                                                 select='value').resources_list

        instance_ids = []
        for node in nodes_ids_resp:
            instance_ids.append(node.json.get('value'))

        self.logger.warning(instance_ids)
        connector_instance.stop_vms_by_ids(instance_ids)

        self.ss_api.cimi_edit(self.deployment['id'], {'state': 'STOPPED'})

        return 0

    def stop_deployment(self):
        self.logger.info('Deployment stop job started for {}.'.format(self.deployment.get('id')))

        self.job.set_progress(10)

        self.handle_deployment()

        return 10000

    def do_work(self):
        self.stop_deployment()
