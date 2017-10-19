#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

from action import action


@action()
def virtual_machine_collect(job):
    return 10000


def main(argv):
    logging.basicConfig(level=logging.DEBUG)

    logging.getLogger("kazoo").setLevel(logging.INFO)
    
    parser = argparse.ArgumentParser(description='Distribute and process "Cloud resources collecting" jobs')

    parser.add_argument('--zk-hosts', dest='zookeeper_hosts',
                        metavar='HOSTS', default='127.0.0.1:2181',
                        help='Coma separated list (CSV) of ZooKeeper hosts to connect')

    parser.add_argument('--threads', dest='number_of_thread', default=1,
                        metavar='#', type=int, help='Number of worker threads to start')

    parser.add_argument('--worker-name', dest='base_worker_name', metavar='NAME',
                        default=names[int(random.uniform(1, len(names)-1))],
                        help='Base name for worker')

    parser.add_argument('--version', action='version', version='v {}'.format(__version__))

    args = parser.parse_args()

    collector = JobController(name=args.base_worker_name,
                              job_generator=job_generator(args.base_worker_name),
                              job_processor=job_processor,
                              number_of_thread=args.number_of_thread,
                              zookeeper_hosts=args.zookeeper_hosts)
    collector.start()



