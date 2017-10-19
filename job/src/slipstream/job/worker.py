#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import sys
import logging
import argparse

if __package__ is None:
    __package__ = 'slipstream.job'
    __import__(__package__)

#from action import *
from .action import get_action
from .controller import JobController, ActionNotImplemented

#from action.virtual_machines_collect import virtual_machine_collect

__version__ = 0.1

logger = logging.getLogger('{}.{}'.format(__package__, __name__))

def job_processor(job):
    if not job or 'action' not in job:
        logger.warning('Invalid job: {}'.format(job))

    action_name = job.get('action')
    action = get_action(action_name)

    if not action:
        raise ActionNotImplemented(action_name)

    logger.debug('Processing job {}'.format(job.job_uri))
    job.set_state('RUNNING')
    try:
        return action(job)
    except:
        logger.exception('Job failed while processing it')
        # TODO: Fail the job or raise something so that the caller fail the job
        raise


def main(argv):
    logging.basicConfig(level=logging.DEBUG)

    logging.getLogger("kazoo").setLevel(logging.INFO)
    logging.getLogger('slipstream').setLevel(logging.DEBUG)
    
    parser = argparse.ArgumentParser(description='Process SlipStream jobs')

    parser.add_argument('--zk-hosts', dest='zk_hosts',
                        metavar='HOSTS', default='127.0.0.1:2181',
                        help='Coma separated list (CSV) of ZooKeeper hosts to connect')

    parser.add_argument('--threads', dest='number_of_thread', default=1,
                        metavar='#', type=int, help='Number of worker threads to start')

    parser.add_argument('--worker-name', dest='base_worker_name', metavar='NAME',
                        default=None,
                        help='Base name for worker')

    parser.add_argument('--ss-url', dest='ss_url',
                        help='SlipStream endpoint to connect to (default: https://nuv.la)',
                        default='https://nuv.la', metavar='URL')

    parser.add_argument('--ss-username', dest='ss_user', help='SlipStream username', metavar='USERNAME')
    parser.add_argument('--ss-password', dest='ss_pass', help='SlipStream Password', metavar='PASSWORD')

    parser.add_argument('--ss-insecure', dest='ss_insecure', default=False, action='store_true',
                        help='Do not check SlipStream certificate')

    parser.add_argument('--version', action='version', version='v {}'.format(__version__))

    args = parser.parse_args()

    controller = JobController(name=args.base_worker_name,
                              ss_username=args.ss_user, ss_password=args.ss_pass, ss_endpoint=args.ss_url,
                              zk_hosts=args.zk_hosts,
                              ss_insecure=args.ss_insecure)

    controller.process_jobs(job_processor, args.number_of_thread)


if __name__ == '__main__':
    main(sys.argv)



