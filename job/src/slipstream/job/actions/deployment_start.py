# -*- coding: utf-8 -*-

from __future__ import print_function

try:
    from itertools import izip as zip  # PY2
except ImportError:
    pass  # PY3

from ..util import load_module
from ..util import classlogger

from ..actions import action

from slipstream.NodeInstance import NodeInstance, NodeDecorator

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


@classlogger
@action('start_deployment')
class DeploymentStartJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.ss_api = executor.ss_api
        self.timeout = 60  # seconds job should terminate in maximum 60 seconds

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

    def _get_user(self):
        deployment_owner = 'khaled'  # FIXME extract deployment owner
        return self.ss_api.cimi_get('user/{}'.format(deployment_owner)).json

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

    # @property
    # def cloud_name(self):
    #     return self.cloud_credential['connector']['href']
    #
    # @property
    # def connector_name(self):
    #     return self.cloud_configuration['cloudServiceType']

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

    def generate_key_secret(self):
        # FIXME: this will create an api key secret with limited scope to the deployment and deployment parameters.
        # the key and secret will be stored in deployment. It will have a special role which allow creation of reports
        #
        # the key is deleted when the deployment is stopped
        # data = {'credentialTemplate': {'href': 'credential-template/generate-api-key',
        #                                'ttl': 0,
        #                                'acl': {'owner': {'principal': self.user,
        #                                                  'type': 'USER'}}}}
        # self.ss_api.cimi_add('credentials', data)
        return 'credential/5449cb4d-fb35-401b-a064-fba89d524a90', 'd7NQ3w.Jt9YLZ.Hr8vV2.hK4KyJ.qvLJcQ'

    def create_deployment_parameter(self, node_id, user, parm_name, param_value=None):
        parameter = {'name': parm_name,
                     'nodeID': node_id,
                     'deployment': {'href': self.deployment['id']},
                     'acl': {'owner': {'principal': 'ADMIN',
                                       'type': 'ROLE'},
                             'rules': [{'principal': user,
                                        'type': 'USER',
                                        'right': 'MODIFY'}]}}  # TODO not always allow modification
        if param_value:
            parameter['value'] = param_value
        return self.ss_api.cimi_add('deploymentParameters', parameter)

    def handle_deployment(self):

        # cf. java server com.sixsq.slipstream.connector.CliConnectorBase.getCommandEnvironment
        # the idea to remove orchestrator so we can start each node as set to it server ssh keys for debug (orch key, this will changed/removed when the node start and fetch the user ssh keys)

        # get slipstream configuration cf. java server com.sixsq.slipstream.connector.CliConnectorBase.getContextualizationEnvironment

        # get references credentials cf. java server com.sixsq.slipstream.connector.CliConnectorBase.extractDeploymentCredentialIds

        # get module owner to create ss api key secret TODO

        # generate ss api key for user cf. java server  com.sixsq.slipstream.connector.CliConnectorBase.genAndSetRunApiKey TODO
        # com.sixsq.slipstream.connector.CliConnectorBase.generateApiKeySecretPair don't forget to set ROLES for credentials

        # each node will be started and will get info of which node it will be

        # state machine will be completly changed, initialization -> no more provisoning -> executing TODO

        # get module the logic of actual orch will be moved here TODO

        # get the cloud connector instance

        # user_info map:
        # {'General.sshPublicKey': '',
        #  'exoscale-ch-gva.domain-name': '',
        #  'exoscale-ch-gva.endpoint': '',
        #  'exoscale-ch-gva.native-contextualization': 'linux-only',
        #  'exoscale-ch-gva.password': 'GNuOcRz4gsVh3d-oZFb4RkcsmzKrcT9VrQgrIlQPmBc',
        #  'exoscale-ch-gva.username': 'EXOe6b5af678776f7d824aef41d',
        #  'exoscale-ch-gva.zone': 'CH-GVA-2'}
        # nodes instance map:
        # {'node-khaled': NodeInstance({'exoscale-ch-gva.disk': '10G', 'exoscale-ch-gva.security.groups': 'slipstream_managed', 'image.platform': 'linux', 'network': 'Public', 'exoscale-ch-gva.networks': '', 'cloudservice': 'exoscale-ch-gva', 'image.id': 'Linux Ubuntu 14.04 LTS 64-bit', 'exoscale-ch-gva.instance.type': 'Micro', 'node_instance_name': 'node-khaled', 'image.loginUser': 'ubuntu', 'image.imageId': 'Linux Ubuntu 14.04 LTS 64-bit'})}
        # get_initialization_extra_kwargs:
        # {}
        #
        #
        # We should update slipstream.cloudconnectors.BaseCloudConnector.BaseCloudConnector#_get_bootstrap_script to not use env variables.
        # This function is used by each connector cloud client at contextualization time.
        #
        # The better is to to add a method 'set_context' to slipstream.NodeInstance.NodeInstance  which will add all env needed variables without using the env

        # start on cloud
        # slipstream.cloudconnectors.BaseCloudConnector.BaseCloudConnector#start_nodes_and_clients

        # for nodes in module:
        # append node_name to create node_instances
        # node_instance_set_context(env var check java cliConnector)

        # publish vm info slipstream.cloudconnectors.BaseCloudConnector.BaseCloudConnector#__add_vm should be moved to new deployment and simplified

        # for node in node_instances:
        # this is temporary, waiting to reorder and simplify everything in connectors
        # extract ip id ssh and set affected resources
        # create node params

        # I should update bootstrap file to support set abort message if error occur
        # I should update client with new workflow to comunicate with new deployment resource

        cloud_credential_id = 'credential/ecab1faf-32f6-4a76-8c2b-f93df4c4f75c'
        cloud_credential = self.ss_api.cimi_get(cloud_credential_id).json
        cloud_name = cloud_credential['connector']['href']
        cloud_configuration = self.ss_api.cimi_get(cloud_name).json
        cloud_instance_name = cloud_configuration['instanceName']
        connector_instance, user_info = \
            DeploymentStartJob.connector_instance_userinfo(cloud_configuration, cloud_credential)

        user_ssh_pub_keys = 'ssh-rsa AAAAB3NzaC1yc2EAAAABJQAAAQEAnRxAn1QdEdHEjgerzI3aBBgezjjG4Zv3FxVRgBuzgog2Px8Zti6g' \
                            '74bjs+iNgabduLZCskc87ZHOb97iDktefrOMrucBqkWVvnC5gFxI4lD8EhrIS0MyqIHm+Flbf2Sr6gjcqCttT1bX' \
                            '7s9vL3LMNw9WZ+6brsufBVg3rexjk2GvbqHcmWV98I5v+KIoSCUwmN2o+ENTL8qWCOO8JPqHmyF9qJYudEC1RU0a' \
                            'lUcA5UVEJYeGsX13unhNEDeZIvAObAh/uIhA6V7GPg803JGwmOClQ0BIPVBudv2mHHQFTms/6NBqK10v5bEGO47N' \
                            'kJb8c+K8sePufd71PxSu77MH4Q== khaled'

        user_info.set_public_keys(user_ssh_pub_keys)

        deployment_ss_key, deployment_ss_secret = self.generate_key_secret()

        deployment_owner = self.deployment['acl']['owner']['principal']

        module = self.deployment['module']

        node_instance_name = 'machine-test'

        node1 = NodeInstance({
            '{}.disk'.format(cloud_instance_name): str(module['content']['disk']),
            '{}.security.groups'.format(cloud_instance_name): 'slipstream_managed',
            '{}.networks'.format(cloud_instance_name): '',
            '{}.instance.type'.format(cloud_instance_name): 'Micro',
            # search for service offer should occur when creating the deployment template
            'image.platform': 'linux',
            'network': module['content']['networkType'],
            'cloudservice': cloud_instance_name,
            'image.id': module['content']['imageIDs'][cloud_instance_name],
            'image.imageId': module['content']['imageIDs'][cloud_instance_name],
            'node_instance_name': node_instance_name,
            'image.loginUser': 'ubuntu'})

        node1_context = {'SLIPSTREAM_DIID': self.deployment.get('id'),
                         'SLIPSTREAM_SERVICEURL': self.slipstream_configuration.get('serviceURL'),
                         'SLIPSTREAM_NODE_INSTANCE_NAME': node_instance_name,
                         'SLIPSTREAM_CLOUD': 'exoscale-ch-gva',
                         'SLIPSTREAM_BUNDLE_URL': self.slipstream_configuration.get('clientURL'),
                         'SLIPSTREAM_BOOTSTRAP_BIN': self.slipstream_configuration.get('clientBootstrapURL'),
                         'SLIPSTREAM_USERNAME': deployment_owner,
                         'SLIPSTREAM_API_KEY': deployment_ss_key,
                         'SLIPSTREAM_API_SECRET': deployment_ss_secret,
                         'SLIPSTREAM_SS_CACHE_KEY': self.deployment.get('id'),
                         'SLIPSTREAM_USER_SSH_PUB_KEYS': user_ssh_pub_keys}

        node1.set_deployment_context(node1_context)
        node_instances = {node_instance_name: node1}
        # need discussion, this is done by thread and allow
        # to limit max_iaas_workers
        initialization_extra_kwargs = {}
        connector_instance.start_nodes_and_clients(user_info, node_instances, initialization_extra_kwargs)

        for node_name, node in node_instances.items():
            self.create_deployment_parameter(node_name, deployment_owner,
                                             NodeDecorator.CLOUD_NODE_ID_KEY, node.get_cloud_node_id())
            self.create_deployment_parameter(node_name, deployment_owner,
                                             NodeDecorator.CLOUD_NODE_IP_KEY, node.get_cloud_node_ip())
            if node.get_cloud_node_ssh_url():
                self.create_deployment_parameter(node_name, deployment_owner,
                                                 NodeDecorator.CLOUD_NODE_SSH_URL_KEY,
                                                 node.get_cloud_node_ssh_url())
            if node.get_cloud_node_ssh_password():
                self.create_deployment_parameter(node_name, deployment_owner,
                                                 NodeDecorator.CLOUD_NODE_SSH_PASSWORD_KEY,
                                                 node.get_cloud_node_ssh_password())
            if node.get_cloud_node_ssh_keypair_name():
                self.create_deployment_parameter(node_name, deployment_owner,
                                                 NodeDecorator.CLOUD_NODE_SSH_KEYPAIR_NAME_KEY,
                                                 node.get_cloud_node_ssh_keypair_name())

        self.ss_api.cimi_edit(self.deployment['id'], {'state': 'STARTED'})

        return 0

    def start_deployment(self):
        self.logger.info('Deployment start job started for {}.'.format(self.deployment.get('id')))

        self.job.set_progress(10)

        self.handle_deployment()

        return 10000

    def do_work(self):
        self.start_deployment()
