# -*- coding: utf-8 -*-

from __future__ import print_function

import time
import logging

from .base import Base


class Distributor(Base):
    def __init__(self):
        super(Distributor, self).__init__()
        Base._init_logger('distributor_{}.log'.format(self._get_jobs_type()))

    def _job_distributor(self):
        logging.info(self._log_msg('I am {} and I have been elected to distribute "{}" jobs'
                                   .format(self.name, self._get_jobs_type())))
        while not self.stop_event.is_set():
            for cimi_job in self.job_generator():
                try:
                    logging.info(self._log_msg('Distribute job: {}'.format(cimi_job)))
                    self.ss_api.cimi_add('jobs', cimi_job)
                except:
                    logging.exception(self._log_msg('Failed to distribute job: {}'.format(cimi_job)))
                    time.sleep(0.1)
        logging.info('Distributor properly stopped.')

    def _start_distribution(self):
        election = self._kz.Election('/election/{}'.format(self._get_jobs_type()), self.name)
        while True:
            logging.info(self._log_msg('STARTING ELECTION'))
            election.run(self._job_distributor)

    # ----- METHOD THAT CAN/SHOULD BE IMPLEMENTED IN DISTRIBUTOR SUBCLASS -----
    def job_generator(self):
        """This is a generator function that produces a sequence of Job(s) to be added to SSCLJ server.
        This function must be override by the user subclass.
        """
        raise NotImplementedError()

    def _get_jobs_type(self):
        raise NotImplementedError()

    def do_work(self):
        logging.info(self._log_msg('I am distributor {}.'.format(self.name)))
        self._start_distribution()
