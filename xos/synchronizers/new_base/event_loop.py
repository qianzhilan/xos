import os
import imp
import inspect
import time
import sys
import traceback
import commands
import threading
import json
import pdb
import pprint
import traceback
from datetime import datetime
from xos.logger import Logger, logging, logger
from xosconfig import Config
from synchronizers.new_base.steps import *
from syncstep import SyncStep, NullSyncStep
from toposort import toposort
from synchronizers.new_base.error_mapper import *
from synchronizers.new_base.steps.sync_object import SyncObject
from synchronizers.new_base.modelaccessor import *

debug_mode = False


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


logger = Logger(level=logging.INFO)


class StepNotReady(Exception):
    pass


class NoOpDriver:
    def __init__(self):
        self.enabled = True
        self.dependency_graph = None


# Everyone gets NoOpDriver by default. To use a different driver, call
# set_driver() below.

DRIVER = NoOpDriver()


def set_driver(x):
    global DRIVER
    DRIVER = x


STEP_STATUS_WORKING = 1
STEP_STATUS_OK = 2
STEP_STATUS_KO = 3


def invert_graph(g):
    ig = {}
    for k, v in g.items():
        for v0 in v:
            try:
                ig[v0].append(k)
            except:
                ig[v0] = [k]
    return ig


class XOSObserver:
    sync_steps = []

    def __init__(self, sync_steps):
        # The Condition object that gets signalled by Feefie events
        self.step_lookup = {}
        self.sync_steps = sync_steps
        self.load_sync_steps()
        self.event_cond = threading.Condition()

        self.driver = DRIVER
        self.observer_name = Config.get("name")

    def wait_for_event(self, timeout):
        self.event_cond.acquire()
        self.event_cond.wait(timeout)
        self.event_cond.release()

    def wake_up(self):
        logger.info('Wake up routine called. Event cond %r' % self.event_cond)
        self.event_cond.acquire()
        self.event_cond.notify()
        self.event_cond.release()

    def load_sync_steps(self):
        dep_path = Config.get("dependency_graph")
        logger.info('Loading model dependency graph from %s' % dep_path)
        try:
            # This contains dependencies between records, not sync steps
            self.model_dependency_graph = json.loads(open(dep_path).read())
            for left, lst in self.model_dependency_graph.items():
                new_lst = []
                for k in lst:
                    try:
                        tup = (k, k.lower())
                        new_lst.append(tup)
                        deps = self.model_dependency_graph[k]
                    except:
                        self.model_dependency_graph[k] = []

                self.model_dependency_graph[left] = new_lst
        except Exception as e:
            raise e

        try:
            # FIXME `pl_dependency_graph` is never defined, this will always fail
            # NOTE can we remove it?
            backend_path = Config.get("pl_dependency_graph")
            logger.info(
                'Loading backend dependency graph from %s' %
                backend_path)
            # This contains dependencies between backend records
            self.backend_dependency_graph = json.loads(
                open(backend_path).read())
            for k, v in self.backend_dependency_graph.items():
                try:
                    self.model_dependency_graph[k].extend(v)
                except KeyError:
                    self.model_dependency_graphp[k] = v

        except Exception as e:
            logger.info('Backend dependency graph not loaded')
            # We can work without a backend graph
            self.backend_dependency_graph = {}

        provides_dict = {}
        for s in self.sync_steps:
            self.step_lookup[s.__name__] = s
            for m in s.provides:
                try:
                    provides_dict[m.__name__].append(s.__name__)
                except KeyError:
                    provides_dict[m.__name__] = [s.__name__]

        step_graph = {}
        phantom_steps = []
        for k, v in self.model_dependency_graph.items():
            try:
                for source in provides_dict[k]:
                    if (not v):
                        step_graph[source] = []

                    for m, _ in v:
                        try:
                            for dest in provides_dict[m]:
                                # no deps, pass
                                try:
                                    if (dest not in step_graph[source]):
                                        step_graph[source].append(dest)
                                except:
                                    step_graph[source] = [dest]
                        except KeyError:
                            if (m not in provides_dict):
                                try:
                                    step_graph[source] += ['#%s' % m]
                                except:
                                    step_graph[source] = ['#%s' % m]

                                phantom_steps += ['#%s' % m]
                            pass

            except KeyError:
                pass
                # no dependencies, pass

        self.dependency_graph = step_graph
        self.deletion_dependency_graph = invert_graph(step_graph)

        pp = pprint.PrettyPrinter(indent=4)
        logger.debug(pp.pformat(step_graph))
        self.ordered_steps = toposort(
            self.dependency_graph, phantom_steps + map(lambda s: s.__name__, self.sync_steps))
        self.ordered_steps = [
            i for i in self.ordered_steps if i != 'SyncObject']

        logger.info("Order of steps=%s" % self.ordered_steps)

        self.load_run_times()

    def check_duration(self, step, duration):
        try:
            if (duration > step.deadline):
                logger.info(
                    'Sync step %s missed deadline, took %.2f seconds' %
                    (step.name, duration))
        except AttributeError:
            # S doesn't have a deadline
            pass

    def update_run_time(self, step, deletion):
        if (not deletion):
            self.last_run_times[step.__name__] = time.time()
        else:
            self.last_deletion_run_times[step.__name__] = time.time()

    def check_schedule(self, step, deletion):
        last_run_times = self.last_run_times if not deletion else self.last_deletion_run_times

        time_since_last_run = time.time() - last_run_times.get(step.__name__, 0)
        try:
            if (time_since_last_run < step.requested_interval):
                raise StepNotReady
        except AttributeError:
            logger.info(
                'Step %s does not have requested_interval set' %
                step.__name__)
            raise StepNotReady

    def load_run_times(self):
        try:
            jrun_times = open(
                '/tmp/%sobserver_run_times' %
                self.observer_name).read()
            self.last_run_times = json.loads(jrun_times)
        except:
            self.last_run_times = {}
            for e in self.ordered_steps:
                self.last_run_times[e] = 0
        try:
            jrun_times = open(
                '/tmp/%sobserver_deletion_run_times' %
                self.observer_name).read()
            self.last_deletion_run_times = json.loads(jrun_times)
        except:
            self.last_deletion_run_times = {}
            for e in self.ordered_steps:
                self.last_deletion_run_times[e] = 0

    def lookup_step_class(self, s):
        if ('#' in s):
            return NullSyncStep
        else:
            step = self.step_lookup[s]
        return step

    def lookup_step(self, s):
        if ('#' in s):
            objname = s[1:]
            so = NullSyncStep()

            obj = model_accessor.get_model_class(objname)

            so.provides = [obj]
            so.observes = [obj]
            step = so
        else:
            step_class = self.step_lookup[s]
            step = step_class(driver=self.driver, error_map=self.error_mapper)
        return step

    def save_run_times(self):
        run_times = json.dumps(self.last_run_times)
        open(
            '/tmp/%sobserver_run_times' %
            self.observer_name,
            'w').write(run_times)

        deletion_run_times = json.dumps(self.last_deletion_run_times)
        open('/tmp/%sobserver_deletion_run_times' %
             self.observer_name, 'w').write(deletion_run_times)

    def check_class_dependency(self, step, failed_steps):
        step.dependenices = []
        for obj in step.provides:
            lst = self.model_dependency_graph.get(obj, [])
            nlst = map(lambda a_b1: a_b1[1], lst)
            step.dependenices.extend(nlst)
        for failed_step in failed_steps:
            if (failed_step in step.dependencies):
                raise StepNotReady

    def sync(self, S, deletion):
        try:
            step = self.lookup_step_class(S)
            start_time = time.time()

            logger.debug(
                "Starting to work on step %s, deletion=%s" %
                (step.__name__, str(deletion)))

            dependency_graph = self.dependency_graph if not deletion else self.deletion_dependency_graph
            # if not deletion else self.deletion_step_conditions
            step_conditions = self.step_conditions
            step_status = self.step_status  # if not deletion else self.deletion_step_status

            # Wait for step dependencies to be met
            try:
                deps = dependency_graph[S]
                has_deps = True
            except KeyError:
                has_deps = False

            go = True

            failed_dep = None
            if (has_deps):
                for d in deps:
                    if d == step.__name__:
                        logger.debug(
                            "   step %s self-wait skipped" %
                            step.__name__)
                        go = True
                        continue

                    cond = step_conditions[d]
                    cond.acquire()
                    if (step_status[d] is STEP_STATUS_WORKING):
                        logger.debug(
                            "  step %s wait on dep %s" %
                            (step.__name__, d))
                        cond.wait()
                        logger.debug(
                            "  step %s wait on dep %s cond returned" %
                            (step.__name__, d))
                    elif step_status[d] == STEP_STATUS_OK:
                        go = True
                    else:
                        logger.debug(
                            "  step %s has failed dep %s" %
                            (step.__name__, d))
                        go = False
                        failed_dep = d
                    cond.release()
                    if (not go):
                        break
            else:
                go = True

            if (not go):
                logger.debug("Step %s skipped" % step.__name__)
                self.failed_steps.append(step)
                my_status = STEP_STATUS_KO
            else:
                sync_step = self.lookup_step(S)
                sync_step.__name__ = step.__name__
                sync_step.dependencies = []
                try:
                    mlist = sync_step.provides

                    try:
                        for m in mlist:
                            lst = self.model_dependency_graph[m.__name__]
                            nlst = map(lambda a_b: a_b[1], lst)
                            sync_step.dependencies.extend(nlst)
                    except Exception as e:
                        raise e

                except KeyError:
                    pass
                sync_step.debug_mode = debug_mode

                should_run = False
                try:
                    # Various checks that decide whether
                    # this step runs or not
                    self.check_class_dependency(
                        sync_step, self.failed_steps)  # dont run Slices if Sites failed
                    # dont run sync_network_routes if time since last run < 1
                    # hour
                    self.check_schedule(sync_step, deletion)
                    should_run = True
                except StepNotReady:
                    logger.info('Step not ready: %s' % sync_step.__name__)
                    self.failed_steps.append(sync_step)
                    my_status = STEP_STATUS_KO
                except Exception as e:
                    logger.error('%r' % e)
                    logger.log_exc(
                        "sync step failed: %r. Deletion: %r" %
                        (sync_step, deletion))
                    self.failed_steps.append(sync_step)
                    my_status = STEP_STATUS_KO

                if (should_run):
                    try:
                        duration = time.time() - start_time

                        logger.debug(
                            'Executing step %s, deletion=%s' %
                            (sync_step.__name__, deletion))

                        failed_objects = sync_step(
                            failed=list(
                                self.failed_step_objects),
                            deletion=deletion)

                        self.check_duration(sync_step, duration)

                        if failed_objects:
                            self.failed_step_objects.update(failed_objects)

                        logger.debug(
                            "Step %r succeeded, deletion=%s" %
                            (sync_step.__name__, deletion))
                        my_status = STEP_STATUS_OK
                        self.update_run_time(sync_step, deletion)
                    except Exception as e:
                        logger.error(
                            'Model step %r failed. This seems like a misconfiguration or bug: %r. This error will not be relayed to the user!' %
                            (sync_step.__name__, e))
                        logger.log_exc("Exception in sync step")
                        self.failed_steps.append(S)
                        my_status = STEP_STATUS_KO
                else:
                    logger.info("Step %r succeeded due to non-run" % step)
                    my_status = STEP_STATUS_OK

            try:
                my_cond = step_conditions[S]
                my_cond.acquire()
                step_status[S] = my_status
                my_cond.notify_all()
                my_cond.release()
            except KeyError as e:
                logger.debug('Step %r is a leaf' % step)
                pass
        finally:
            try:
                model_accessor.reset_queries()
            except:
                # this shouldn't happen, but in case it does, catch it...
                logger.log_exc("exception in reset_queries")

            model_accessor.connection_close()

    def run(self):
        if not self.driver.enabled:
            return

        while True:
            logger.debug('Waiting for event')
            self.wait_for_event(timeout=5)
            logger.debug('Observer woke up')

            self.run_once()

    def run_once(self):
        try:
            model_accessor.check_db_connection_okay()

            loop_start = time.time()
            error_map_file = Config.get('error_map_path')
            self.error_mapper = ErrorMapper(error_map_file)

            # Two passes. One for sync, the other for deletion.
            for deletion in [False, True]:
                # Set of individual objects within steps that failed
                self.failed_step_objects = set()

                # Set up conditions and step status
                # This is needed for steps to run in parallel
                # while obeying dependencies.

                providers = set()
                dependency_graph = self.dependency_graph if not deletion else self.deletion_dependency_graph

                for v in dependency_graph.values():
                    if (v):
                        providers.update(v)

                self.step_conditions = {}
                self.step_status = {}

                for p in list(providers):
                    self.step_conditions[p] = threading.Condition()

                    self.step_status[p] = STEP_STATUS_WORKING

                self.failed_steps = []

                threads = []
                logger.debug('Deletion=%r...' % deletion)
                schedule = self.ordered_steps if not deletion else reversed(
                    self.ordered_steps)

                for S in schedule:
                    thread = threading.Thread(
                        target=self.sync, name='synchronizer', args=(
                            S, deletion))

                    logger.debug('Deletion=%r...' % deletion)
                    threads.append(thread)

                # Start threads
                for t in threads:
                    t.start()

                # another spot to clean up debug state
                try:
                    model_accessor.reset_queries()
                except:
                    # this shouldn't happen, but in case it does, catch it...
                    logger.log_exc("exception in reset_queries")

                # Wait for all threads to finish before continuing with the run
                # loop
                for t in threads:
                    t.join()

            self.save_run_times()

            loop_end = time.time()

            model_accessor.update_diag(
                loop_end=loop_end,
                loop_start=loop_start,
                backend_status="1 - Bottom Of Loop")

        except Exception as e:
            logger.error(
                'Core error. This seems like a misconfiguration or bug: %r. This error will not be relayed to the user!' %
                e)
            logger.log_exc("Exception in observer run loop")
            traceback.print_exc()
            model_accessor.update_diag(backend_status="2 - Exception in Event Loop")
