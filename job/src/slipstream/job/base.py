# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import logging
from logging.handlers import RotatingFileHandler
import random
import sys
import threading
import signal
from functools import partial
from kazoo.client import KazooClient, KazooRetry
from slipstream.api import Api

from .util import assure_path_exists, print_stack

names = ['Cartman', 'Kenny', 'Stan', 'Kyle', 'Butters', 'Token', 'Timmy', 'Wendy', 'M. Garrison', 'Chef',
         'Randy', 'Ike', 'Mr. Mackey', 'Mr. Slave', 'Tweek', 'Craig']

LOG_FILENAME = '/var/log/slipstream/job.log'


class Base(object):
    def __init__(self):
        self.args = None
        self._init_args_parser()
        self._kz = None
        self.ss_api = None
        self.name = None
        self.stop_event = threading.Event()

        signal.signal(signal.SIGTERM, partial(Base.on_exit, self.stop_event))
        signal.signal(signal.SIGINT, partial(Base.on_exit, self.stop_event))
        signal.signal(signal.SIGUSR1, print_stack)

    def _init_args_parser(self):
        parser = argparse.ArgumentParser(description='Process SlipStream jobs')
        required_args = parser.add_argument_group('required named arguments')

        parser.add_argument('--zk-hosts', dest='zk_hosts',
                            metavar='HOSTS', default='127.0.0.1:2181',
                            help='Coma separated list of ZooKeeper hosts to connect (default: 127.0.0.1:2181)')

        parser.add_argument('--ss-url', dest='ss_url',
                            help='SlipStream endpoint to connect to (default: https://nuv.la)',
                            default='https://nuv.la', metavar='URL')

        required_args.add_argument('--ss-user', dest='ss_user', help='SlipStream username',
                                   metavar='USERNAME', required=True)
        required_args.add_argument('--ss-pass', dest='ss_pass', help='SlipStream Password',
                                   metavar='PASSWORD', required=True)

        parser.add_argument('--ss-insecure', dest='ss_insecure', default=False, action='store_true',
                            help='Do not check SlipStream certificate')

        parser.add_argument('--name', dest='name', metavar='NAME', default=None, help='Base name for this process')

        self._set_command_specific_options(parser)

        self.args = parser.parse_args()

    def _set_command_specific_options(self, parser):
        pass

    @staticmethod
    def _init_logger(log_filename):
        filename = '/var/tmp/{}'.format(log_filename)
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        logging.getLogger('kazoo').setLevel(logging.WARN)
        logging.getLogger('elasticsearch').setLevel(logging.WARN)
        logging.getLogger('slipstream').setLevel(logging.INFO)
        logging.getLogger('urllib3').setLevel(logging.WARN)
        logging.getLogger('stopit').setLevel(logging.ERROR)
        assure_path_exists(filename)
        handler_file = RotatingFileHandler(filename, mode='a', maxBytes=10485760, backupCount=5)
        log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)s - %(message)s')
        handler_file.setFormatter(log_format)
        handler_console = logging.StreamHandler()
        handler_console.setFormatter(log_format)
        logger.addHandler(handler_file)
        logger.addHandler(handler_console)

    def _log_msg(self, message, name=None):
        return ' {} - {}'.format(name or self.name, message)

    @staticmethod
    def on_exit(stop_event, signum, frame):
        print('\n\nExecution interrupted by the user!')
        stop_event.set()
        sys.exit(0)

    def do_work(self):
        raise NotImplementedError()

    def execute(self):
        self.name = self.args.name if self.args.name is not None else names[int(random.uniform(1, len(names) - 1))]

        self.ss_api = Api(endpoint=self.args.ss_url, insecure=self.args.ss_insecure, reauthenticate=True)
        self.ss_api.login_internal(self.args.ss_user, self.args.ss_pass)

        self._kz = KazooClient(self.args.zk_hosts, connection_retry=KazooRetry(max_tries=-1),
                               command_retry=KazooRetry(max_tries=-5), timeout=30.0)
        self._kz.start()

        self.do_work()

        while True:
            signal.pause()


def main(command):
    try:
        command().execute()
    except Exception as e:
        logging.exception(e)
        exit(2)
