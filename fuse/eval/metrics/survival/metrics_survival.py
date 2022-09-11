"""
(C) Copyright 2021 IBM Corp.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Created on June 30, 2021

"""

from functools import partial
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union, Hashable
import traceback

import numpy as np

from fuse.eval.metrics.libs.survival import MetricsSurvival
from fuse.eval.metrics.metrics_common import MetricDefault



class MetricCIndex(MetricDefault):
    """
    Compute c-index (concordance index) score using lifelines
    """

    def __init__(
        self,
        pred: str,
        event_times: str,
        event_observed: Optional[str]=None,
        **kwargs,
    ):
        """
        See MetricDefault for the missing params
        :param pred: a length-n iterable prediction scores
        :param event_times:  a length-n iterable event times, or censor times if event is not observed.
        :param event_observed: a length-n iterable event observed flags, 1 if observed, 0 if not (i.e. censored). Default None assumes all observed.
        """
        super().__init__(pred=pred, target=None, event_times=event_times, event_observed=event_observed, 
                         metric_func=MetricsSurvival.c_index, **kwargs)


