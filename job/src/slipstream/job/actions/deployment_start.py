# -*- coding: utf-8 -*-

from __future__ import print_function

try:
    from itertools import izip as zip  # PY2
except ImportError:
    pass  # PY3

from ..util import load_module, connector_classes

from ..actions import action

from slipstream.NodeInstance import NodeInstance, NodeDecorator

import logging
import uuid


@action('start_deployment')
class DeploymentStartJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.ss_api = executor.ss_api

        self._deployment = None
        self._module = None
        self._cloud_name = None
        self._cloud_credential = None
        self._cloud_configuration = None
        self._slipstream_configuration = None
        self._user = None
        self._user_params = None
        self._connector_name = None
        self._connector_instance = None
        self.deployment_owner = self.deployment['acl']['owner']['principal']

    def _get_deployment(self):
        return self.ss_api.cimi_get(self.job['targetResource']['href']).json

    def _get_slipstream_configuration(self):
        return self.ss_api.cimi_get('configuration/slipstream').json

    def _get_user(self):
        return self.ss_api.cimi_get('user/{}'.format(self.deployment_owner)).json

    def _get_user_params(self):
        user_params = self.ss_api.cimi_search('userParam',
                                              filter='acl/owner/principal="{}"'.format(self.deployment_owner))
        return user_params.resources_list[0].json

    @property
    def cloud_credential(self):
        if self._cloud_credential is None:
            self._cloud_credential = self.ss_api.cimi_get('credential/cf30a7fa-6504-433e-934b-318fe92f3bcb').json
        return self._cloud_credential

    @property
    def deployment(self):
        if self._deployment is None:
            self._deployment = self._get_deployment()
        return self._deployment

    @property
    def module(self):
        if self._module is None:
            self._module = self.deployment['module']
        return self._module

    @staticmethod
    def connector_instance_userinfo(cloud_configuration, cloud_credential):
        connector_name = cloud_configuration['cloudServiceType']
        connector = load_module(connector_classes[connector_name])
        if not hasattr(connector, 'instantiate_from_cimi'):
            raise NotImplementedError('The connector "{}" is not compatible with the start_deployment job'
                                      .format(cloud_configuration['cloudServiceType']))
        return connector.instantiate_from_cimi(cloud_configuration, cloud_credential), \
               connector.get_user_info_from_cimi(cloud_configuration, cloud_credential)

    @property
    def slipstream_configuration(self):
        if self._slipstream_configuration is None:
            self._slipstream_configuration = self._get_slipstream_configuration()
        return self._slipstream_configuration

    @property
    def user(self):
        if self._user is None:
            self._user = self._get_user()
        return self._user

    @property
    def user_params(self):
        if self._user_params is None:
            self._user_params = self._get_user_params()
        return self._user_params

    def create_deployment_parameter(self, user, param_name, param_value=None, node_id=None, param_description=None):
        parameter = {'name': param_name,
                     'deployment': {'href': self.deployment['id']},
                     'acl': {'owner': {'principal': 'ADMIN',
                                       'type': 'ROLE'},
                             'rules': [{'principal': user,
                                        'type': 'USER',
                                        'right': 'MODIFY'}]}}  # TODO not always allow modification
        if node_id:
            parameter['nodeID'] = node_id
        if param_description:
            parameter['description'] = param_description
        if param_value:
            parameter['value'] = param_value
        return self.ss_api.cimi_add('deploymentParameters', parameter)

    @staticmethod
    def kb_from_data_uuid(text):
        class NullNameSpace:
            bytes = b''

        return str(uuid.uuid3(NullNameSpace, text))

    def __contruct_deployment_param_href(self, node_id, param_name):
        param_id = ':'.join(item or '' for item in [self.deployment['id'], node_id, param_name])
        return 'deployment-parameter/' + self.kb_from_data_uuid(param_id)

    def set_deployment_parameter(self, param_name, param_value, node_id=None):
        deployment_parameter_href = self.__contruct_deployment_param_href(node_id, param_name)
        self.ss_api.cimi_edit(deployment_parameter_href, {'value': param_value})

    @staticmethod
    def lookup_recursively_module(module, keys):  # FIXME: support for array of maps
        temp = module
        for k in keys[:-1]:
            temp = temp.get(k, {})
        value = temp.get(keys[-1])
        if value:
            return value
        module_parent = module.get('content', {}).get('parent')
        if module_parent:
            return DeploymentStartJob.lookup_recursively_module(module_parent, keys)

    @staticmethod
    def get_node_parameters(module):
        all_module_params_merged = {}
        local_module = module
        while local_module:
            params = local_module.get('outputParameters', []) + local_module.get('inputParameters', [])
            for param in params:
                param_name = param['parameter']
                if param_name in all_module_params_merged:
                    param.update(all_module_params_merged[param_name])
                all_module_params_merged[param_name] = param
            local_module = local_module.get('parent', {}).get('content', None)
        return all_module_params_merged

    def create_deployment_parameters(self, node_name, node_params):
        # Global service params
        deployment_owner = self.deployment['acl']['owner']['principal']
        for param in self.deployment['outputParameters']:
            self.create_deployment_parameter(user=deployment_owner,
                                             param_name=param['parameter'],
                                             param_value=param.get('value'),
                                             node_id=None,
                                             param_description=param['description'])

        for param in node_params:
            self.create_deployment_parameter(user=deployment_owner,
                                             param_name=param['parameter'],
                                             param_value=param.get('value'),
                                             node_id=node_name,
                                             param_description=param['description'])

    def handle_deployment(self):
        node_instance_name = 'machine-{}'.format(self.deployment['id'].replace('deployment/', ''))
        node_params = self.get_node_parameters(self.module['content'])
        self.create_deployment_parameters(node_instance_name, node_params.values())
        cloud_credential_id = node_params['credential.id']['value']
        published_ports = node_params['cloud.node.publish.ports'].get('value', None)

        cloud_credential = self.ss_api.cimi_get(cloud_credential_id).json
        cloud_href = cloud_credential['connector']['href']

        cloud_configuration = self.ss_api.cimi_get(cloud_href).json
        cloud_instance_name = cloud_configuration['instanceName']
        connector_instance, user_info = DeploymentStartJob.connector_instance_userinfo(cloud_configuration,
                                                                                       cloud_credential)

        ssh_pub_key = self.user_params.get('sshPublicKey')

        user_info.set_public_keys(ssh_pub_key)

        self.ss_api.cimi_edit(self.deployment['id'], {'sshPublicKeys': ssh_pub_key})

        deployment_owner = self.deployment['acl']['owner']['principal']

        module = self.deployment['module']

        cpu = DeploymentStartJob.lookup_recursively_module(module, ['content', 'cpu'])
        ram = DeploymentStartJob.lookup_recursively_module(module, ['content', 'ram'])
        disk = DeploymentStartJob.lookup_recursively_module(module, ['content', 'disk'])
        image_id = DeploymentStartJob.lookup_recursively_module(module, ['content', 'imageIDs', cloud_instance_name])
        network_type = DeploymentStartJob.lookup_recursively_module(module, ['content', 'networkType'])
        login_user = DeploymentStartJob.lookup_recursively_module(module, ['content', 'loginUser'])

        node = NodeInstance({
            '{}.cpu'.format(cloud_instance_name): str(cpu),
            '{}.ram'.format(cloud_instance_name): str(ram),
            '{}.disk'.format(cloud_instance_name): str(disk),
            '{}.publish'.format(cloud_instance_name): published_ports.split() if published_ports else [],
            '{}.security.groups'.format(cloud_instance_name): 'slipstream_managed',
            '{}.networks'.format(cloud_instance_name): '',
            '{}.instance.type'.format(cloud_instance_name): 'Micro',
            'image.platform': 'linux',
            'network': network_type,
            'cloudservice': cloud_instance_name,
            'image.id': image_id,
            'image.imageId': image_id,
            'node_instance_name': node_instance_name,
            'image.loginUser': login_user
        })

        node_context = {'SLIPSTREAM_DIID': self.deployment.get('id'),
                        'SLIPSTREAM_SERVICEURL': self.slipstream_configuration.get('serviceURL'),
                        'SLIPSTREAM_NODE_INSTANCE_NAME': node_instance_name,
                        'SLIPSTREAM_CLOUD': cloud_instance_name,
                        'SLIPSTREAM_BUNDLE_URL': self.slipstream_configuration.get('clientURL')
                            .replace('.tgz', '-cimi.tgz'),
                        'SLIPSTREAM_BOOTSTRAP_BIN': self.slipstream_configuration.get('clientBootstrapURL')
                            .replace('.bootstrap', '-cimi.bootstrap'),
                        'SLIPSTREAM_USERNAME': deployment_owner,
                        'SLIPSTREAM_API_KEY': self.deployment['clientApiKey']['href'],
                        'SLIPSTREAM_API_SECRET': self.deployment['clientApiKey']['secret'],
                        'SLIPSTREAM_SS_CACHE_KEY': self.deployment.get('id')
                        }

        node.set_deployment_context(node_context)

        connector_instance._BaseCloudConnector__start_node_instance_and_client(user_info, node)

        if node.get_cloud_node_ssh_url():
            self.set_deployment_parameter('url.ssh', node.get_cloud_node_ssh_url(), node_instance_name)

        if node.get_cloud_node_ssh_password():
            self.set_deployment_parameter('password.ssh', node.get_cloud_node_ssh_password(), node_instance_name)

        if node.get_cloud_node_ssh_keypair_name():
            self.set_deployment_parameter('keypair.name', node.get_cloud_node_ssh_keypair_name(), node_instance_name)

        if node.get_cloud_node_ports_mapping():
            self.create_deployment_parameter(deployment_owner, NodeDecorator.CLOUD_NODE_PORTS_MAPPING_KEY,
                                             node.get_cloud_node_ports_mapping(), node_instance_name,
                                             "Published ports mappings")

        self.set_deployment_parameter('hostname', node.get_cloud_node_ip(), node_instance_name)
        self.set_deployment_parameter(NodeDecorator.INSTANCEID_KEY, node.get_instance_id(), node_instance_name)

        self.ss_api.cimi_edit(self.deployment['id'], {'state': 'STARTED'})

        return 0

    def start_deployment(self):
        logging.info('Deployment start job started for {}.'.format(self.deployment.get('id')))

        self.job.set_progress(10)

        try:
            self.handle_deployment()
        except:
            self.ss_api.cimi_edit(self.deployment['id'], {'state': 'ERROR'})
            raise

        return 10000

    def do_work(self):
        self.start_deployment()
