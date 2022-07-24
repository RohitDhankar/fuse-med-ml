from enum import Enum
from typing import Any, Callable, Union

import numpy as np
import pandas as pd


class DukeLabelType(Enum):
    ispCR = "ispCR"
    STAGING_TUMOR_SIZE = "Staging Tumor Size"
    HISTOLOGY_TYPE = "Histology Type"
    IS_HIGH_TUMOR_GRADE_TOTAL = "is High Tumor Grade Total"

    def get_value(self, clinical_features: pd.DataFrame) -> Any:  # fix type Any
        col_name = self.get_column_name()
        value = clinical_features[col_name]
        process_func = self.get_process_func()
        if process_func is None:
            return value
        if isinstance(value, pd.Series):
            value = value.apply(process_func)
        else:
            value = process_func(value)
        return value

    def select_features(self, clinical_features: pd.DataFrame) -> pd.DataFrame:  # todo: ask Tal
        group1 = [
            "MRI Findings:Skin/Nipple Invovlement",  # 'Skin Invovlement',
            "US features:Tumor Size (cm)",  # 'Tumor Size US',
            "Mammography Characteristics:Tumor Size (cm)",  # 'Tumor Size MG',
            "MRI Technical Information:FOV Computed (Field of View) in cm ",  # 'Field of View',
            "MRI Technical Information:Contrast Bolus Volume (mL)",  # 'Contrast Bolus Volume',
            "Demographics:Race and Ethnicity",  # 'Race',
            "MRI Technical Information:Manufacturer Model Name",  # 'Manufacturer',
            "MRI Technical Information:Slice Thickness",  # 'Slice Thickness']
        ]
        if self in (DukeLabelType.ispCR, DukeLabelType.STAGING_TUMOR_SIZE):
            fnames = group1
        elif self == DukeLabelType.HISTOLOGY_TYPE:
            fname = "MRI Findings:Multicentric/Multifocal"  # 'Multicentric'
            fnames = group1 + [fname]
        elif self == DukeLabelType.IS_HIGH_TUMOR_GRADE_TOTAL:
            fnames = [
                "Mammography Characteristics:Breast Density",  # 'Breast Density MG',
                "Tumor Characteristics:PR",  # 'PR',
                "Tumor Characteristics:HER2",  # 'HER2',
                "Tumor Characteristics:ER",  # 'ER']
            ]
        else:
            raise NotImplementedError(self)
        return clinical_features[fnames]

    def get_column_name(self) -> str:
        if self == DukeLabelType.ispCR:
            return "Near Complete Response:Overall Near-complete Response:  Stricter Definition"  # 'Near pCR Strict'
        if self == DukeLabelType.STAGING_TUMOR_SIZE:
            return "Tumor Characteristics:Staging(Tumor Size)# [T]"  # 'Staging Tumor Size'
        if self == DukeLabelType.HISTOLOGY_TYPE:
            return "Tumor Characteristics:Histologic type"  # 'Histologic type'
        # if self == DukeLabelType.IS_HIGH_TUMOR_GRADE_TOTAL:
        #     return 'Tumor Grade Total'
        raise NotImplementedError(self)

    def get_process_func(self) -> Callable:
        if self == DukeLabelType.ispCR:

            def update_func(ispCR: int) -> Union[np.Nan, int]:  # fix return type
                if ispCR > 2:
                    return np.NaN
                if ispCR == 0 or ispCR == 2:
                    return 0
                else:
                    return 1

            return update_func

        if self == DukeLabelType.STAGING_TUMOR_SIZE:
            return lambda val: 1 if val > 1 else 0

        if self == DukeLabelType.HISTOLOGY_TYPE:

            def update_func(histology_type: int) -> Union[np.Nan, int]:  # fix return type
                if histology_type == 1:
                    return 0
                elif histology_type == 10:
                    return 1
                else:
                    return np.NaN

            return update_func

        if self == DukeLabelType.IS_HIGH_TUMOR_GRADE_TOTAL:
            return lambda grade: 1 if grade >= 7 else 0
        raise NotImplementedError(self)

    def get_num_classes(self) -> int:
        return 2  # currrently all are binary classification tasks
