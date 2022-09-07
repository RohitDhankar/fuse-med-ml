from fuse.utils.ndict import NDict
import os
import numpy as np
from medcam import medcam
import cv2
import nibabel as nib
from multiprocessing import Pool
from tqdm import tqdm
import pandas as pd
import torch.nn as nn
import torch
import pqdm

class ModelWrapDictToSeq(torch.nn.Module):
    """
    Fuse model wrapper for wrapping fuse pytorch model and make him be in basic format- input is tensor and output is tensor
    The user need to provide the input and output keys of the fuse model
    """

    def __init__(self, fuse_model: torch.nn.Module, output_key: str, input_key: str):
        super().__init__()
        self.model = fuse_model
        self.output_key = output_key
        self.input_key = input_key

    def forward(self, input: torch.tensor):
        batch_dict = NDict()
        # find input key
        batch_dict[self.input_key] = input
        # feed fuse model with dict as he excpect
        ans_ndict = self.model(batch_dict)
        # extract model output from dict
        output = NDict(ans_ndict)[self.output_key]
        return output


def save_attention_centerpoint(pl_module ,  infer_dataloader , explain: NDict) :
    if not os.path.isdir(explain['centerpoints_dir_name']):
        os.mkdir(explain['centerpoints_dir_name'])
    if not os.path.isdir(explain['attention_dir']):
        os.mkdir(explain['attention_dir'])
    device="cuda:0"
    # os.environ["CUDA_VISIBLE_DEVICES"] = "0, 1, 2 ,3,4,5,6,7"
    model = ModelWrapDictToSeq(pl_module._model,input_key ='data.input.img', output_key='output.head_0').to(device)
    model = medcam.inject(model, output_dir=os.path.join(explain['attention_dir']),label=explain['label'], backend='gcam', save_maps=True, layer='auto', return_attention=explain['debug']).to(device)
    results = []
    i = 0
    try: 
        for batch in tqdm(infer_dataloader, total=len(infer_dataloader)):
            try: 
                # if isinstance(batch['data.input.img'], list) :
                #     batch['data.input.img'] = torch.stack(batch['data.input.img'])
                #     batch['data.gt.classification'] = torch.stack(batch['data.gt.classification'] )
                batch['data.input.img'] = batch['data.input.img'].to(device)
                batch['data.gt.classification'] = batch['data.gt.classification'].to(device)
                if explain['debug'] == True:
                    logit, attention = model(batch['data.input.img'])
                else:
                    logit = model(batch['data.input.img'])
                logit_vector = logit
                params = []
                for j in range(0,batch['data.input.img'].shape[0]) :
                    sample =  batch['data.input.img'][j][0].cpu()
                    logit = logit_vector[j][explain['target_int']]
                    label = str(batch['data.gt.classification'][j])
                    if explain['debug'] == True:
                        attention_map = attention[j][0].cpu()
                    else:
                        attention_map = None
                    identifier = batch['data.input.img_path'][j].replace('*','')
                    param = {"i": i ,"logit":logit, "attention_map":attention_map ,"j": j ,"sample" : sample , "explain":explain , "identifier" : identifier, "label":label}
                    res = run_gradcam_on_sample(param)
                    results.append(res)
                    #results.append(pqdm(params , run_gradcam_on_sample, n_jobs = explain["num_workers"]))
                i += 1
                params.append(param)
            except Exception as e:
                    print("got problem in batch containing the following examples",batch['data.input.img_path'])
                    print(e)
                    continue     
            
    except Exception as e:
        print(e)
        df = pd.DataFrame(results, columns=["identifier","logit","dist", "big_point"])
        df.to_csv("prostate_output.csv")  
        pass
    df = pd.DataFrame(results, columns=["identifier","logit","dist", "big_point"])
    df.to_csv("prostate_output.csv")   
def run_gradcam_on_sample(params):
    i = params["i"]
    logit = params["logit"]
    j = params["j"]
    batch = params["j"]
    explain = params["explain"]
    sample = params["sample"]
    sample = sample.numpy()
    layer_folder = [name for name in os.listdir(explain['attention_dir']) if os.path.isdir(os.path.join(explain['attention_dir'], name))][0]
    original_attention_name =  os.path.join(explain['attention_dir'],layer_folder, 'attention_map_' + str(i) + '_'+str(j)+'_0.nii.gz')
    original_attention_map = nib.load(original_attention_name).get_fdata()
    original_transposed = np.transpose(sample, axes=(1, 2, 0))
    scale_ratio = [original_transposed.shape[i] / value for i, value in enumerate(original_attention_map.shape)]
    points = []
    max_value = original_attention_map.argmax()
    current_max = max_value
    index = 0
    while index < 5:
        current_max = original_attention_map.argmax()
        max_volume = np.unravel_index(current_max, original_attention_map.shape)
        if current_max < max_value:
            break
        points.append(np.asarray(max_volume))
        original_attention_map[max_volume] = 0.0
        index += 1
    points = np.array(points)
    big_point = np.array([int(np.mean(points[:,i])*scale_ratio[i]) for i in range(3)])
    identifier = params["identifier"]
    with open(os.path.join(explain['centerpoints_dir_name'],identifier+'.npy'), 'wb') as f:
        np.save(f, big_point)
    center = np.array([int(index / 2) for index in original_transposed.shape])
    dist = np.linalg.norm(big_point - center)
    # if logit < 0.9 and dist > 40 : 
    #     print(identifier,"suspected as wrong")
    #     print("logit",logit,"distate from center",dist,"center=",center)
    if explain['debug'] == True:
        attention_map = params["attention_map"]
        attention_map = attention_map.numpy()
        identifier = identifier.replace('*','')
        attention_map = show_attention_on_image(sample, attention_map)
        sample = np.transpose(sample, axes=(1, 2, 0))
        original = nib.Nifti1Image(sample, affine=np.eye(4))
        nib.save(original, filename=os.path.join(explain['attention_dir'],'original_'+identifier+'_'+str(big_point)+'.nii.gz'))
        nib.save(attention_map, filename=os.path.join(explain['attention_dir'],'attention_'+identifier+'_'+'.nii.gz'))
    return [identifier,logit,dist, big_point]



def show_attention_on_image(img: np.ndarray,
                            mask: np.ndarray,
                            colormap: int = cv2.COLORMAP_JET) -> np.ndarray:
    """ This function overlays the cam mask on the image as an heatmap.
    reference for fusing heat map and original image : https://github.com/jacobgil/pytorch-grad-cam/blob/61e9babae8600351b02b6e90864e4807f44f2d4a/pytorch_grad_cam/utils/image.py#L25
    By default the heatmap is in BGR format.
    :param img: The base image in RGB or BGR format.
    :param mask: The cam mask.
    :param colormap: The OpenCV colormap to be used.
    :returns: The default image with the cam overlay.
    """
    heatmaps = [np.float32(cv2.applyColorMap(np.uint8(255 * mask[i]), colormap)) / 255 for i in range(mask.shape[0])]
    images = [cv2.cvtColor(img[i], cv2.COLOR_GRAY2RGB) for i in range(img.shape[0])]
    RGB_DTYPE = np.dtype([('R', 'u1'), ('G', 'u1'), ('B', 'u1')])
    cams = []
    for i in range(len(images)):
        if np.max(images[i]) > 1:
            images[i] *= (1.0 / images[i].max())

        cam = heatmaps[i] + images[i]
        cam = cam / np.max(cam)
        cam = np.uint8(255 * cam)
        cam = cam.view(RGB_DTYPE)
        cams.append(cam)
    nifti = nib.Nifti1Image(np.concatenate(cams, axis=2), np.eye(4))
    return nifti
