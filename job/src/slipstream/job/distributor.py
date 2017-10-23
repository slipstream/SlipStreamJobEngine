# -*- coding: utf-8 -*-

from __future__ import print_function

import time

from .base import Base
from .util import classlogger


@classlogger
class Distributor(Base):
    def __init__(self):
        super(Distributor, self).__init__()

    def _job_distributor(self):
        self.logger.info(self._log_msg('I ({}) am the leader (I have been elected)'.format(self.name)))
        while True:
            for cimi_job in self.job_generator():
                try:
                    self.logger.info(self._log_msg('Distribute job: {}'.format(cimi_job)))
                    self.ss_api.cimi_add('jobs', cimi_job)
                except:
                    self.logger.exception(self._log_msg('Failed to distribute job: {}'.format(cimi_job)))
                    time.sleep(0.1)

    def _start_distribution(self):
        election = self._kz.Election('/election/{}'.format(self._get_jobs_type()), self.name)
        while True:
            self.logger.info(self._log_msg('STARTING ELECTION'))
            election.run(self._job_distributor, self._job_generator)

    # ----- METHOD THAT CAN/SHOULD BE IMPLEMENTED IN DISTRIBUTOR SUBCLASS -----
    def _job_generator(self):
        """This is a generator function that produces a sequence of Job(s) to be added to SSCLJ server.
        This function must be override by the user subclass.
        """
        raise NotImplementedError()

    def _get_jobs_type(self):
        raise NotImplementedError()

    def do_work(self):
        self.logger.info(self._log_msg('I am {} distributor.'.format(self.name)))
        self._start_distribution()
