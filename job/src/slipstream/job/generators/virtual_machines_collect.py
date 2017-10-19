#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import sys
import time
import logging
import argparse

from ..controller import JobController

__version__ = 0.1

class VirtualMachinesCollectJobGenerator(object):

    def __init__(self, ss_api, collect_interval=60):
        self.ss_api = ss_api
        self.collect_interval = collect_interval

    def __call__(self):
        return self.virtual_machines_collect_job_generator()

    def _get_credentials(self):
        response = self.ss_api.cimi_search('credentials', filter='type^="cloud-cred"')
        return response.json.get('credentials')

    def _time_spent(self, start_time):
        return time.time() - start_time

    def _time_left(self, start_time):
        return self.collect_interval - self._time_spent(start_time)

    def virtual_machines_collect_job_generator(self):
        while True:
            start_time = time.time()

            credentials = self._get_credentials()
            nb_credentials = len(credentials)

            yield_interval = float(self.collect_interval) / float(nb_credentials) * 0.6

            for credential in credentials:
                job = {'action': 'collect_virtual_machines',
                       'targetResource': {'href': credential['id']}}
                yield job

                time.sleep(yield_interval)
            time.sleep(self._time_left(start_time))


def main(argv):
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description='Process SlipStream jobs')

    parser.add_argument('--name', dest='name', metavar='NAME', default=None, help='Base name for this process')

    parser.add_argument('--zk-hosts', dest='zk_hosts',
                        metavar='HOSTS', default='127.0.0.1:2181',
                        help='Coma separated list (CSV) of ZooKeeper hosts to connect')

    parser.add_argument('--ss-url', dest='ss_url',
                        help='SlipStream endpoint to connect to (default: https://nuv.la)',
                        default='https://nuv.la', metavar='URL')

    parser.add_argument('--ss-username', dest='ss_user', help='SlipStream username', metavar='USERNAME')
    parser.add_argument('--ss-password', dest='ss_pass', help='SlipStream Password', metavar='PASSWORD')

    parser.add_argument('--ss-insecure', dest='ss_insecure', default=False, action='store_true',
                        help='Do not check SlipStream certificate')

    parser.add_argument('--version', action='version', version='v {}'.format(__version__))

    args = parser.parse_args()

    controller = JobController(name=args.name,
                               ss_username=args.ss_user, ss_password=args.ss_pass, ss_endpoint=args.ss_url,
                               zk_hosts=args.zk_hosts,
                               ss_insecure=args.ss_insecure)

    job_generator = VirtualMachinesCollectJobGenerator(controller.ss_api)

    controller.distribute_jobs('virtual_machines_collect_job', job_generator)


if __name__ == '__main__':
    main(sys.argv)
