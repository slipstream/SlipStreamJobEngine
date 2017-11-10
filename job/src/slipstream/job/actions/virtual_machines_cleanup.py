# -*- coding: utf-8 -*-

from __future__ import print_function

from ..util import classlogger
from ..actions import action

import datetime


@classlogger
@action('cleanup_virtual_machines')
class VirtualMachinesCleanupJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.ss_api = executor.ss_api

    def cleanup_jobs(self):
        self.logger.info('Cleanup of virtual machines started.')

        date_minus_1_hour = (datetime.datetime.utcnow() - datetime.timedelta(hours=1)).isoformat() + 'Z'
        filter_vms_str = 'updated<"{}"'.format(date_minus_1_hour)
        vms_not_updated = self.ss_api.cimi_search('virtualMachines', filter=filter_vms_str)
        self.logger.info('Number of virtual machines to be cleaned up: {}'.format(vms_not_updated.count))

        vms_deleted = []
        for vm in vms_not_updated.resources_list:
            self.logger.debug('Cleanup of virtual machine {}.'.format(vm.json.get('id')))
            self.ss_api.cimi_delete(vm.json.get('id'))
            vms_deleted.append(vm.json.get('id'))

        msg = 'Cleanup of virtual machines finished. Removed {} virtual machines.'.format(vms_not_updated.count)
        self.logger.info(msg)
        self.job.add_affected_resources(vms_deleted)
        self.job.set_status_message(msg)

        return 10000

    def do_work(self):
        self.cleanup_jobs()
