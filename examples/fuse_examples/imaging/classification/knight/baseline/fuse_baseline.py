from collections import OrderedDict
import pathlib
from fuse.utils.utils_logger import fuse_logger_start
import os
import sys
# add parent directory to path, so that 'baseline' folder is treated as a module
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from baseline.dataset import knight_dataset
import pandas as pd
from fuse.dl.models.model_default import ModelDefault
from fuse.dl.models.backbones.backbone_resnet_3d import BackboneResnet3D
from fuse.dl.models.heads.head_3D_classifier import Head3dClassifier
from fuse.dl.losses.loss_default import LossDefault
import torch.nn.functional as F
import torch.nn as nn
from fuse.eval.metrics.classification.metrics_classification_common import MetricAUCROC, MetricAccuracy, MetricConfusion
from fuse.eval.metrics.classification.metrics_thresholding_common import MetricApplyThresholds
import torch.optim as optim
from fuse.dl.managers.manager_default import ManagerDefault
from fuse.dl.managers.callbacks.callback_tensorboard import TensorboardCallback
from fuse.dl.managers.callbacks.callback_metric_statistics import MetricStatisticsCallback
import fuse.utils.gpu as GPU
from fuse.utils.rand.seed import Seed
import logging
import time

## Parameters:
##############################################################################
# Data sources to use in model. Set {'imaging': True, 'clinical': False} for imaging only setting,
# and vice versa, or set both to True to use both.
# allocate gpus
# uncomment if you want to use specific gpus instead of automatically looking for free ones
task_num = 1 # 1 or 2
force_gpus = [0,1] # specify the GPU indices you want to use
use_data = {'imaging': True, 'clinical': True} # specify whether to use imaging, clinical data or both
batch_size = 2
resize_to = (256, 256, 110) 
print_and_visualize = True

if task_num == 1:
    num_epochs = 100
    num_classes = 2
    learning_rate = 1e-4 if use_data['clinical'] else 1e-5
    imaging_dropout = 0.5
    clinical_dropout = 0.0
    fused_dropout = 0.5
    target_name='data.gt.gt_global.task_1_label'
    target_metric='metrics.auc'

elif task_num == 2:
    num_epochs = 150
    num_classes = 5
    learning_rate = 1e-4
    imaging_dropout = 0.7
    clinical_dropout = 0.0
    fused_dropout = 0.0
    target_name='data.gt.gt_global.task_2_label'
    target_metric='metrics.auc.macro_avg'

def main():
    # read train/val splits file. for convenience, we use the one
    # auto-generated by the nnU-Net framework for the KiTS21 data
    dir_path = pathlib.Path(__file__).parent.resolve()
    splits=pd.read_pickle(os.path.join(dir_path, 'splits_final.pkl'))
    # For this example, we use split 0 out of the 5 available cross validation splits
    split = splits[0]

    # read environment variables for data, cache and results locations
    data_path = os.environ['KNIGHT_DATA']
    cache_path = os.environ['KNIGHT_CACHE']
    results_path = os.environ['KNIGHT_RESULTS'] 

    ## Basic settings:
    ##############################################################################
    # create model results dir:
    # we use a time stamp in model directory name, to prevent re-writing
    timestr = time.strftime("%Y%m%d-%H%M%S")
    model_dir = os.path.join(results_path, timestr)
    if not os.path.isdir(model_dir):
        os.makedirs(model_dir)

    # start logger
    fuse_logger_start(output_path=model_dir, console_verbose_level=logging.INFO)
    print("Done")

    # set constant seed for reproducibility. 
    os.environ['CUBLAS_WORKSPACE_CONFIG']=":4096:8" # required for pytorch deterministic mode
    rand_gen = Seed.set_seed(1234, deterministic_mode=True)

    # select gpus
    GPU.choose_and_enable_multiple_gpus(len(force_gpus), force_gpus=force_gpus)

    ## FuseMedML dataset preparation
    ##############################################################################

    train_dl, valid_dl, _, _, _, _ = knight_dataset(data_dir=data_path, cache_dir=cache_path, split=split, \
                reset_cache=False, rand_gen=rand_gen, batch_size=batch_size, resize_to=resize_to, \
                task_num=task_num, target_name=target_name, num_classes=num_classes)

    ## Simple data visualizations/analysis:
    ##############################################################################

    if print_and_visualize:
        # an example of printing a sample from the data:
        sample_index = 10
        #print(train_dl.dataset[sample_index]['data']['input']['clinical']['all'])
        print(train_dl.dataset[sample_index])

        # print a summary of the label distribution:
        #print(train_dl.dataset.summary(["data.gt.gt_global.task_1_label"]))
        #print(valid_dl.dataset.summary(["data.gt.gt_global.task_1_label"]))

        # visualize a sample 
        # this will only do anything if a matplotlib gui backend is set appropriately, or in "notebook mode"
        train_dl.dataset.visualize(sample_index)

        # visualize a sample with augmentations applied:
        train_dl.dataset.visualize_augmentation(sample_index)

    ## Model definition
    ##############################################################################

    if use_data['imaging']:
        backbone = BackboneResnet3D(in_channels=1)
        conv_inputs = [('model.backbone_features', 512)]
    else:
        backbone = nn.Identity()
        conv_inputs = None
    if use_data['clinical']:
        append_features = [("data.input.clinical.all", 11)]
    else:
        append_features = None

    model = ModelDefault(
        conv_inputs=(('data.input.image', 1),),
        backbone=backbone,
        heads=[
            Head3dClassifier(head_name='head_0',
                                conv_inputs=conv_inputs,
                                dropout_rate=imaging_dropout, 
                                num_classes=num_classes,
                                append_features=append_features,
                                append_layers_description=(256,128),
                                append_dropout_rate=clinical_dropout,
                                fused_dropout_rate=fused_dropout
                                ),
        ]
    )

    # Loss definition:
    ##############################################################################
    losses = {
        'cls_loss': LossDefault(pred='model.logits.head_0', target=target_name,
                                    callable=F.cross_entropy, weight=1.0)
    }

    # Metrics definition:
    ##############################################################################
    metrics = OrderedDict([
        ('op', MetricApplyThresholds(pred='model.output.head_0')), # will apply argmax
        ('auc', MetricAUCROC(pred='model.output.head_0', target=target_name)),
        ('accuracy', MetricAccuracy(pred='results:metrics.op.cls_pred', target=target_name)),
        ('sensitivity', MetricConfusion(pred='results:metrics.op.cls_pred', target=target_name, metrics=('sensitivity',))),

    ])

    best_epoch_source = {
        'source': target_metric,  # can be any key from losses or metrics dictionaries
        'optimization': 'max',  # can be either min/max
    }

    # Optimizer definition:
    ##############################################################################
    optimizer = optim.Adam(model.parameters(), lr=learning_rate,
                            weight_decay=0.001)         
                            
    # Scheduler definition:
    ##############################################################################
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer)

    ## Training
    ##############################################################################

    # set tensorboard callback
    callbacks = {
        TensorboardCallback(model_dir=model_dir), # save statistics for tensorboard
        MetricStatisticsCallback(output_path=model_dir + "/metrics.csv"),  # save statistics a csv file

    }
    manager = ManagerDefault(output_model_dir=model_dir, force_reset=True)
    manager.set_objects(net=model,
                        optimizer=optimizer,
                        losses=losses,
                        metrics=metrics,
                        best_epoch_source=best_epoch_source,
                        lr_scheduler=scheduler,
                        callbacks=callbacks,
                        train_params={'num_epochs': num_epochs, 'lr_sch_target': 'train.losses.total_loss'}, # 'lr_sch_target': 'validation.metrics.auc.macro_avg'
                        output_model_dir=model_dir)

    print('Training...')            
    manager.train(train_dataloader=train_dl,
                    validation_dataloader=valid_dl)


if __name__ == "__main__":
    main()