# -*- coding: utf-8 -*-

from __future__ import print_function

import logging
from threading import Thread

from elasticsearch import Elasticsearch

from .actions import get_action, ActionNotImplemented
from .base import Base
from .job import Job, NonexistentJobError
from .util import classlogger
from .util import override
import stopit

@classlogger
class Executor(Base):
    def __init__(self):
        super(Executor, self).__init__()
        self.es = None

    @override
    def _set_command_specific_options(self, parser):
        parser.add_argument('--threads', dest='number_of_thread', default=1,
                            metavar='#', type=int, help='Number of worker threads to start (default: 1)')
        parser.add_argument('--es-hosts-list', dest='es_hosts_list', default=['localhost'],
                            nargs='+', metavar='HOST', help='Elasticsearch list of hosts (default: [localhost])')

    def _process_jobs(self, thread_name):
        queue = self._kz.LockingQueue('/job')
        while not self.stop_event.is_set():
            job_uri = None
            try:
                job_uri = queue.get()

                if job_uri is None:
                    self.logger.debug(self._log_msg('No job available. Waiting ...'))
                    self.stop_event.wait(0.1)
                    continue

                job = Job(self.ss_api, job_uri)

                if job.get('state') in Job.final_states:
                    self.logger.warning(self._log_msg('Job {} in final state; will throw it.').format(job_uri))
                    queue.consume()
                    continue

                self.logger.info(self._log_msg('Executing job "{}" ...'.format(job_uri), name=thread_name))

                try:
                    return_code = self.job_processor(job)
                except ActionNotImplemented as e:
                    self.logger.exception(self._log_msg('Action "{}" not implemented'.format(str(e))))
                    queue.consume()
                    # Consume not implemented action to avoid queue to be filled with not implemented actions
                    msg = 'Not implemented action!'.format(job_uri)
                    status_message = '{}: {}'.format(msg, str(e))
                    job.update_job(state='FAILED', status_message=status_message)
                    # TODO: The idea was to release, perhaps another executor have this action implemented
                    # self._queue.release()
                except Exception as e:
                    msg = 'Failed to process job {}'.format(job_uri)
                    self.logger.exception(self._log_msg(msg))
                    queue.consume()
                    status_message = '{}: {}'.format(msg, str(e))
                    job.update_job(state='FAILED', status_message=status_message)
                    self.stop_event.wait(0.1)
                else:
                    job.update_job(state='SUCCESS', return_code=return_code)
                    queue.consume()
                    self.logger.info(self._log_msg('Job "{}" finished'.format(job_uri), name=thread_name))
            except NonexistentJobError as e:
                self.logger.warning(self._log_msg('Job does not exist; removing from queue. Message: {}').format(e.reason))
                queue.consume()
                continue
            except:
                self.logger.exception('Fatal error when trying to handle job "{}"'.format(job_uri))
        self.logger.info('Thread {} properly stopped.'.format(thread_name))

    def job_processor(self, job):
        if not job or 'action' not in job:
            logging.warning('Invalid job: {}'.format(job))

        action_name = job.get('action')
        action = get_action(action_name)

        if not action:
            raise ActionNotImplemented(action_name)

        self.logger.debug(self._log_msg('Processing job {}'.format(job.job_uri)))
        job.set_state('RUNNING')
        try:
            action_instance = action(self, job)
            with stopit.ThreadingTimeout(action_instance.timeout, swallow_exc=False):
                return action_instance.do_work()
        except stopit.TimeoutException:
            self.logger.exception(self._log_msg('Job "{}" timeout during execution.'.format(job.job_uri)))
            raise Exception('Timeout during execution.')
        except:
            self.logger.exception(self._log_msg('Job "{}" failed during processing.'.format(job.job_uri)))
            # TODO: Fail the job or raise something so that the caller fail the job
            raise

    @override
    def do_work(self):
        self.logger.info(self._log_msg('I am executor {}.'.format(self.name)))
        self.es = Elasticsearch(self.args.es_hosts_list)
        for i in range(1, self.args.number_of_thread + 1):
            th_name = 'job_processor_{}'.format(i)
            th = Thread(target=self._process_jobs, name=th_name, args=(th_name,))
            th.start()
