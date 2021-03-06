# SlipStreamJobEngine

SlipStream job engine use cimi job resource and zookeeper as a locking
queue. It's done in a way to be horizontally scalled on different nodes.

Facts:

- Each action should be distributed by a standalone distributor
- More than one distributor for the same action can be started on different nodes but one will be elected to distribute the job (action).
- Executor load actions dynamically at his startup
- Zookeeper is used as a Locking queue containing only job uuid in /job/entries
- Running jobs are put in zookeeper under /job/taken
- If executor is unable to communicate with CIMI, the job in running state is released (put back in zookeeper queue).
- The action implementation should take care if necessary to continue the execution or to make the cleanup of a unfinshed running job
- If connection is lost with zookeeper /job/taken (executing jobs) will be released because this is ephemeral nodes.
- Stopping the executor will try to make a proper shuttdown by waiting 2 minutes before killing the process. Each thread that terminate his running action will not take a new one.

## Run the slipstream executor

Install the rpm of SlipStreamJobEngine

Create a file `/etc/default/slipstream-job-executor` with following content:
```
DAEMON_ARGS='--ss-url=https://<CIMI_ENDPOINT>:<CIMI_PORT> --ss-user=super --ss-pass=<SUPER_PASS> --zk-hosts=<ZOOKEEPER_ENDPOINT>:<ZOOKEEPER_PORT> --threads=8 --es-hosts-list=<ELASTICSEARCH_ENDPOINTS>'
```

Start the service with `systemctl start slipstream-job-executor`

## Run the slipstream distributors

Install the rpm of SlipStreamJobEngine

Create a file `/etc/default/slipstream-job-distributor` with following content:
```
DAEMON_ARGS='--ss-url=https://<CIMI_ENDPOINT>:<CIMI_PORT> --ss-user=super --ss-pass=<SUPER_PASS> --zk-hosts=<ZOOKEEPER_ENDPOINT>:<ZOOKEEPER_PORT>'
```

Start the service with `systemctl start slipstream-job-distributor@<DISTRIBUTOR_SCRIPT_FILENAME_LAST_PART>`

*e.g systemctl start slipstream-job-distributor@jobs_cleanup.service*

## Implement new actions

To implement new actions to be executed by job executor, you have to
create a class equivalent to actions/dummy_test_action.py. You have to
restart the job executor to force it reload implemented actions.

To create a new action distributor, which will create a cimi job every
x time. Create a class equivalent to
scripts/job_distributor_dummy_test_action.py.


## Logging

Check `/var/log/slipstream/log/` folder.

## Debugging

You can get a trace-back of all running threads using tools like `https://pyrasite.readthedocs.io`

0. `pip install pyrasite`

1. Get python process PID of the executor e.g.

2. Connect to slipstream bash session: `su - slipstream`

3. pyrasite-shell <PID>

4. print traceback with entering code below into pyrasite repl
```
import sys
import threading
import traceback

for th in threading.enumerate():
    print(th)
    traceback.print_stack(sys._current_frames()[th.ident])
    print()
```
