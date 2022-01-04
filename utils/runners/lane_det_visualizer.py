import os

import torch
import numpy as np
from tqdm import tqdm
from abc import abstractmethod
if torch.__version__ >= '1.6.0':
    from torch.cuda.amp import autocast
else:
    from ..torch_amp_dummy import autocast

from .base import BaseVisualizer, get_collate_fn
from ..datasets import DATASETS
from ..transforms import TRANSFORMS
from ..lane_det_utils import lane_as_segmentation_inference
from ..vis_utils import lane_detection_visualize_batched, save_images


def lane_label_process_fn(label):
    # The CULane format
    # input: label txt file path or content as list
    if isinstance(label, str):
        with open(label, 'r') as f:
            label = f.readlines()
    target = []
    for line in label:
        temp = [float(x) for x in line.strip().split(' ')]
        target.append(np.array(temp).reshape(-1, 2))

    return target


class LaneDetVisualizer(BaseVisualizer):
    dataset_tensor_statistics = ['keypoint_color']

    @torch.no_grad()
    def lane_inference(self, images):
        with autocast(self._cfg['mixed_precision']):
            if self._cfg['seg']:
                keypoints = self.model.inference(images,
                                                 [self._cfg['input_size'], self._cfg['original_size']],
                                                 self._cfg['gap'],
                                                 self._cfg['ppl'],
                                                 self._cfg['dataset_name'],
                                                 self._cfg['max_lane'])
            else:  # Seg methods
                keypoints = lane_as_segmentation_inference(self.model, images,
                                                           [self._cfg['input_size'], self._cfg['original_size']],
                                                           self._cfg['gap'],
                                                           self._cfg['ppl'],
                                                           self._cfg['thresh'],
                                                           self._cfg['dataset_name'],
                                                           self._cfg['max_lane'])

        return [[np.array(lane) for lane in image] for image in keypoints]

    @abstractmethod
    def run(self, *args, **kwargs):
        pass

    @abstractmethod
    def get_loader(self, *args, **kwargs):
        pass


class LaneDetDir(LaneDetVisualizer):
    dataset_tensor_statistics = ['colors', 'keypoint_color']

    def __init__(self, cfg):
        super().__init__(cfg)
        os.makedirs(self._cfg['save_path'], exist_ok=True)

    def get_loader(self, cfg):
        if 'vis_dataset' in cfg.keys():
            dataset_cfg = cfg['vis_dataset']
        else:
            dataset_cfg = dict(
                name='ImageFolderLaneDataset',
                root_image=self._cfg['image_path'],
                root_keypoint=self._cfg['keypoint_path'],
                root_mask=self._cfg['mask_path'],
                root_output=self._cfg['save_path'],
                image_suffix=self._cfg['image_suffix'],
                keypoint_suffix=self._cfg['mask_suffix'],
                mask_suffix=self._cfg['keypoint_suffix']
            )
        dataset = DATASETS.from_dict(dataset_cfg,
                                     transforms=TRANSFORMS.from_dict(cfg['test_augmentation']),
                                     target_process_fn=lane_label_process_fn)
        collate_fn = get_collate_fn('dict_collate_fn')  # Use dicts for customized target
        dataloader = torch.utils.data.DataLoader(dataset=dataset,
                                                 batch_size=self._cfg['batch_size'],
                                                 collate_fn=collate_fn,
                                                 num_workers=self._cfg['workers'],
                                                 shuffle=False)

        return dataset, dataloader

    def run(self):
        for imgs, original_imgs, targets in tqdm(self.dataloader):
            filenames = [i['filename'] for i in targets]
            keypoints = [i['keypoints'] for i in targets]
            masks = [i['masks'] for i in targets]
            if keypoints.count(None) == len(keypoints):
                keypoints = None
            if masks.count(None) == masks:
                masks = None
            if self._cfg['pred']:  # Inference keypoints
                keypoints = self.lane_inference(imgs)
            results = lane_detection_visualize_batched(original_imgs,
                                                       masks=masks,
                                                       keypoints=keypoints,
                                                       mask_colors=self._cfg['colors'],
                                                       keypoint_color=self._cfg['keypoint_color'],
                                                       std=None, mean=None)
            save_images(results, filenames=filenames)


class LaneDetVideo(BaseVisualizer):
    def __init__(self, cfg):
        super().__init__(cfg)

    def get_loader(self, cfg):
        pass

    def run(self):
        pass


class LaneDetDataset(BaseVisualizer):
    def __init__(self, cfg):
        super().__init__(cfg)

    def get_loader(self, cfg):
        pass

    def run(self):
        pass