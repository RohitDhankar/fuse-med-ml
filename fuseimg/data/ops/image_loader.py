import os
from fuse.data.ops.op_base import OpBase
from typing import Optional
import numpy as np
import pandas as pd
from fuse.data.ops.ops_common import OpApplyTypes
import nibabel as nib
from fuse.utils.ndict import NDict
import skimage.io as io
import pydicom

class OpLoadImage(OpBase):
    '''
    Loads a medical image, currently only nii is supported
    '''
    def __init__(self, dir_path: str, **kwargs):
        super().__init__(**kwargs)
        self._dir_path = dir_path

    def __call__(self, sample_dict: NDict, op_id: Optional[str], key_in:str, key_out: str, format:str="infer"):
        '''
        :param key_in: the key name in sample_dict that holds the filename
        :param key_out: 
        '''
        img_filename = os.path.join(self._dir_path, sample_dict[key_in])
        img_filename_suffix = img_filename.split(".")[-1]
        if (format == "infer" and img_filename_suffix in ["nii"]) or \
            (format in ["nii", "nib"]):  
            img = nib.load(img_filename)
            img_np = img.get_fdata()
        else:
            raise Exception(f"OpLoadImage: case format {format} and {img_filename_suffix} is not supported")
        
        sample_dict[key_out] = img_np

        return sample_dict

    def reverse(self, sample_dict: NDict, key_to_reverse: str, key_to_follow: str, op_id: Optional[str]) -> dict:        
        return sample_dict 
    
    
class OpLoadDicom(OpBase):
    '''
    Loads a medical image, currently only nii is supported
    '''
    def __init__(self, dir_path: str , **kwargs):
        super().__init__(**kwargs)
        self._dir_path = dir_path

    def __call__(self, sample_dict: NDict, op_id: Optional[str], key_in:str, key_out: str, format:str="infer"):
        '''
        :param key_in: the key name in sample_dict that holds the filename
        :param key_out: 
        '''
        img_filename = os.path.join(self._dir_path, sample_dict[key_in])
        img_filename_suffix = img_filename.split(".")[-1]
        if (format == "infer" and img_filename_suffix in ["dcm"]) or \
            (format in ["nii", "nib"]):  
            dcm = pydicom.dcmread(img_filename)
            inner_image = dcm.pixel_array
            # convert to numpy
            img_np = np.asarray(inner_image)
        else:
            raise Exception(f"OpLoadImage: case format {format} and {img_filename_suffix} is not supported")
        
        sample_dict[key_out] = img_np

        return sample_dict

    def reverse(self, sample_dict: NDict, key_to_reverse: str, key_to_follow: str, op_id: Optional[str]) -> dict:        
        return sample_dict 
    
class OpDownloadImage(OpBase):
    '''
    Loads a medical image, currently only nii is supported
    '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __call__(self, sample_dict: NDict, op_id: Optional[str], key_in:str, key_out: str, format:str="infer"):
        '''
        :param key_in: the key name in sample_dict that holds the filename
        :param key_out: 
        '''
        img_np = io.imread(sample_dict[key_in])
        
        sample_dict[key_out] = img_np

        return sample_dict

    def reverse(self, sample_dict: NDict, key_to_reverse: str, key_to_follow: str, op_id: Optional[str]) -> dict:        
        return sample_dict           
