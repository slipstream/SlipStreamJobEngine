#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

from slipstream.util import loadModule as load_module

from ..action import action

connector_classes = {
    'azure'                  : 'slipstream_azure.AzureClientCloud',
    'cloudstack'             : 'slipstream_cloudstack.CloudStackClientCloud',
    'cloudstackadvancedzone' : 'slipstream_cloudstack.CloudStackAdvancedZoneClientCloud',
    'ec2'                    : 'slipstream_ec2.Ec2ClientCloud',
    'exoscale'               : 'slipstream_exoscale.ExoscaleClientCloud',
    'nuvlabox'               : 'slipstream_nuvlabox.NuvlaBoxClientCloud',
    'opennebula'             : 'slipstream_opennebula.OpenNebulaClientCloud',
    'openstack'              : 'slipstream_openstack.OpenStackClientCloud',
    'otc'                    : 'slipstream_otc.OpenTelekomClientCloud',
    'softlayer'              : 'slipstream_nativesoftlayer.NativeSoftLayerClientCloud',
    'stratuslab'             : 'slipstream_stratuslab.StratusLabClientCloud',
    'stratuslabiter'         : 'slipstream_stratuslab.StratusLabIterClientCloud',
}


@action('collect_virtual_machines')
class VirtualMachinesCollectJob(object):

    def __init__(self, job):
        self.job = job
        self.ss_api = job.ss_api

        self._cloud_name = None
        self._cloud_credential = None
        self._cloud_configuration = None
        self._connector_name = None

        self.collect_virtual_machines()

    def _get_cloud_credential(self):
        return self.ss_api.cimi_get(self.job['targetResource']['href']).json

    def _get_cloud_configuration(self):
        return self.ss_api.cimi_get(self.cloud_name).json

    @property
    def cloud_credential(self):
        if self._cloud_credential is None:
            self._cloud_credential = self._get_cloud_credential()
        return self._cloud_credential

    @property
    def cloud_name(self):
        return self.cloud_credential['name']

    @property
    def connector_name(self):
        return self.cloud_configuration['cloudServiceType']

    @property
    def connector(self):
        return load_module(connector_classes[self.connector_name])

    @property
    def cloud_configuration(self):
        if self._cloud_configuration is None:
            self._cloud_configuration = self._get_cloud_configuration()
        return self._cloud_configuration


    def collect_virtual_machines(self):
        connector = self.connector

        if not hasattr(connector, 'instantiate_from_cimi'):
            raise NotImplementedError('The connector "{}" is not compatible with the collect_virtual_machines job'\
                                      .format(self.connector_name))

        connector_instance = connector.instantiate_from_cimi(self.cloud_configuration, self.cloud_credential)
        for vm in connector_instance.list_instances():
            self.handle_vm(vm)

        return 10000

    def handle_vm(self, vm):
        print(vm)


