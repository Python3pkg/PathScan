import multiprocessing
import time
import logging
import queue
import os.path
import fnmatch

import fss.constants
import fss.config.workers
import fss.workers.controller_base
import fss.workers.worker_base

_LOGGER = logging.getLogger(__name__)


class FilterWorker(fss.workers.worker_base.WorkerBase):
    """This class knows how to recursively traverse a path to produce a list of 
    file-paths.
    """

    def __init__(self, filter_rules, *args):
        super(FilterWorker, self).__init__(*args)

        self.log(logging.INFO, "Creating filter.")

        # We expect this to be a listof 3-tuples: 
        #
        #     (entry-type, filter-type, pattern)
        
        self.__filter_rules = {
            fss.constants.FT_DIR: {
                fss.constants.FILTER_INCLUDE: [],
                fss.constants.FILTER_EXCLUDE: [],
            },
            fss.constants.FT_FILE: {
                fss.constants.FILTER_INCLUDE: [],
                fss.constants.FILTER_EXCLUDE: [],
            },
        }

        for (entry_type, filter_type, pattern) in filter_rules:
            self.__filter_rules[entry_type][filter_type].append(pattern)

        # If an include filter was given for DIRECTORIES, but no exclude 
        # filter, exclude everything but what hits on the include.

        rules = self.__filter_rules[fss.constants.FT_DIR]
        if rules[fss.constants.FILTER_INCLUDE] and \
           not rules[fss.constants.FILTER_EXCLUDE]:
            rules[fss.constants.FILTER_EXCLUDE].append('*')

        # If an include filter was given for FILES, but no exclude filter, 
        # exclude everything but what hits on the include.

        rules = self.__filter_rules[fss.constants.FT_FILE]
        if rules[fss.constants.FILTER_INCLUDE] and \
           not rules[fss.constants.FILTER_EXCLUDE]:
            rules[fss.constants.FILTER_EXCLUDE].append('*')

    def __check_to_permit(self, entry_type, entry_filename):
        """Applying the filter rules."""

        rules = self.__filter_rules[entry_type]

        # Should explicitly include?
        for pattern in rules[fss.constants.FILTER_INCLUDE]:
            if fnmatch.fnmatch(entry_filename, pattern):
                return True

        # Should explicitly exclude?
        for pattern in rules[fss.constants.FILTER_EXCLUDE]:
            if fnmatch.fnmatch(entry_filename, pattern):
                return False

        # Implicitly include.
        return True

    def process_item(self, item):
        (entry_type, entry_path) = item

        entry_filename = os.path.basename(entry_path)
        if self.__check_to_permit(entry_type, entry_filename) is True:
            self.push_to_output((entry_type, entry_path))

    def get_upstream_component_name(self):
        return fss.constants.PC_GENERATOR

    def get_component_name(self):
        return fss.constants.PC_FILTER


class FilterController(fss.workers.controller_base.ControllerBase):
    def __init__(self, filter_rules, *args, **kwargs):
        super(FilterController, self).__init__(*args, **kwargs)

        args = (
            filter_rules,
            self.pipeline_state, 
            self.input_q, 
            self.output_q,
            self.log_q, 
            self.quit_ev 
        )

        self.__p = multiprocessing.Process(target=_boot, args=args)

    def start(self):
        _LOGGER.info("Starting filter.")
        self.__p.start()

    def stop(self):
        _LOGGER.info("Stopping filter.")

        self.quit_ev.set()
# TODO(dustin): Audit for a period of time, and then stop it.
        self.__p.join()

    @property
    def output_queue_size(self):
        return fss.config.workers.FILTER_MAX_OUTPUT_QUEUE_SIZE

def _boot(filter_rules, pipeline_state, input_q, output_q, log_q, quit_ev):
    _LOGGER.info("Booting filter worker.")

    f = FilterWorker(
            filter_rules, 
            pipeline_state, 
            input_q,
            output_q, 
            log_q, 
            quit_ev)

    f.run()
