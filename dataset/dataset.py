import os
import math
import cv2 as cv
import numpy as np
import random
import torch
from torch.utils.data import Dataset
from torchvision import transforms


class AdaMattingDataset(Dataset):

    def __init__(self, raw_data_path, mode):
        self.crop_size = 320
        self.mode = mode
        self.raw_data_path = raw_data_path

        self.fg_path = os.path.join(self.raw_data_path, "train/fg/")
        self.bg_path = os.path.join(self.raw_data_path, "train/bg/")
        self.a_path = os.path.join(self.raw_data_path, "train/mask/")

        data_transforms = {
            # values from ImageNet
            'train': transforms.Compose([
                transforms.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.25),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]),
            'valid': transforms.Compose([
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
            ]),
        }
        self.transformer = data_transforms[self.mode]

        with open(os.path.join(self.raw_data_path, "Combined_Dataset/Training_set/training_fg_names.txt")) as f:
            self.fg_files = f.read().splitlines()
        with open(os.path.join(self.raw_data_path, "Combined_Dataset/Training_set/training_bg_names.txt")) as f:
            self.bg_files = f.read().splitlines()

        filename = "dataset/{}_names.txt".format(self.mode)
        with open(filename, 'r') as file:
            self.names = file.read().splitlines()
    

    def __len__(self):
        return len(self.names)
    

    def __getitem__(self, index):
        name = self.names[index]
        fcount = int(name.split('.')[0].split('_')[0])
        bcount = int(name.split('.')[0].split('_')[1])
        im_name = self.fg_files[fcount]
        bg_name = self.bg_files[bcount]
        fg = cv.imread(self.fg_path + im_name)
        alpha = cv.imread(self.a_path + im_name, 0)
        bg = cv.imread(self.bg_path + bg_name)

        # Resize randomly if in training mode
        resize_factor = 0.75 * random.random() + 0.75 if self.mode == "train" else 1.0
        interpolation = cv.INTER_AREA if resize_factor <= 1 else cv.INTER_LINEAR
        fg = cv.resize(fg, None, fx=resize_factor, fy=resize_factor, interpolation=interpolation)
        alpha = cv.resize(alpha, None, fx=resize_factor, fy=resize_factor , interpolation=interpolation)

        # Rotate randomly in training mode
        if self.mode == "train":
            angle = random.randint(-45, 45)
            fg = self.rotate_cv_image(fg, angle)
            alpha = self.rotate_cv_image(alpha, angle)

        # Flip randomly in training mode
        if self.mode == "train" and random.random() > 0.5:
            fg = np.fliplr(fg)
            alpha = np.fliplr(alpha)
        if self.mode == "train" and random.random() > 0.5:
            bg = np.fliplr(bg)
        
        # Generate gt_trimap
        gt_trimap = np.zeros(alpha.shape, np.float32)
        gt_trimap.fill(128)
        gt_trimap[alpha == 0] = 0
        gt_trimap[alpha == 255] = 255

        # Generate input_trimap
        k_size = random.randint(5, 29) if self.mode == "train" else 15
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k_size, k_size))
        eroded = cv.erode(gt_trimap, kernel)
        dilated = cv.dilate(gt_trimap, kernel)
        input_trimap = np.zeros(gt_trimap.shape, np.float32)
        input_trimap.fill(128)
        input_trimap[eroded == 255] = 255
        input_trimap[dilated == 0] = 0

        # Crop randomly if in training mode
        if self.mode == "train":
            different_size = random.randint(self.crop_size, 800)
            crop_size = (different_size, different_size)
            x, y = self.random_crop_pos(gt_trimap, crop_size)
            gt_alpha = self.do_crop(alpha, x, y, crop_size)
            fg = self.do_crop(fg, x, y, crop_size)
            input_trimap = self.do_crop(input_trimap, x, y, crop_size)
        else:
            gt_alpha = alpha
        
        # Resize and crop the bg to fit the fg
        h, w = fg.shape[:2]
        bh, bw = bg.shape[:2]
        wratio = w / bw
        hratio = h / bh
        ratio = wratio if wratio > hratio else hratio
        if ratio > 1:
            bg = cv.resize(src=bg, dsize=(math.ceil(bw * ratio), math.ceil(bh * ratio)), interpolation=cv.INTER_LINEAR)
        bh, bw = bg.shape[:2]
        x = random.randint(0, bw - w - 1) if self.mode == "train" and bw > w else 0
        y = random.randint(0, bh - h - 1) if self.mode == "train" and bh > h else 0
        bg = np.array(bg[y:y + h, x:x + w], np.float32)

        # Composite the merged image
        normalized_alpha = np.zeros((h, w, 1), np.float32)
        normalized_alpha[:, :, 0] = gt_alpha / 255.
        input_img = normalized_alpha * fg + (1 - normalized_alpha) * bg
        input_img = input_img.astype(np.uint8)

        # Resize if in validation mode
        if self.mode == "valid":
            h, w = input_img.shape[:2]
            if h > w:
                input_img = cv.resize(input_img, (int(w * self.crop_size / h), self.crop_size), interpolation=cv.INTER_AREA)
                input_trimap = cv.resize(input_trimap, (int(w * self.crop_size / h), self.crop_size), interpolation=cv.INTER_AREA)
                gt_alpha = cv.resize(gt_alpha, (int(w * self.crop_size / h), self.crop_size), interpolation=cv.INTER_AREA)
                left_border = int((self.crop_size - input_img.shape[1]) / 2)
                right_border = self.crop_size - input_img.shape[1] - left_border
                input_img = cv.copyMakeBorder(input_img, 0, 0, left_border, right_border, cv.BORDER_CONSTANT, value=[0, 0, 0])
                input_trimap = cv.copyMakeBorder(input_trimap, 0, 0, left_border, right_border, cv.BORDER_CONSTANT, value=[0, 0, 0])
                gt_alpha = cv.copyMakeBorder(gt_alpha, 0, 0, left_border, right_border, cv.BORDER_CONSTANT, value=[0, 0, 0])
            else:
                input_img = cv.resize(input_img, (self.crop_size, int(h * self.crop_size / w)), interpolation=cv.INTER_AREA)
                input_trimap = cv.resize(input_trimap, (self.crop_size, int(h * self.crop_size / w)), interpolation=cv.INTER_AREA)
                gt_alpha = cv.resize(gt_alpha, (self.crop_size, int(h * self.crop_size / w)), interpolation=cv.INTER_AREA)
                top_border = int((self.crop_size - input_img.shape[0]) / 2)
                bottom_border = self.crop_size - input_img.shape[0] - top_border
                input_img = cv.copyMakeBorder(input_img, top_border, bottom_border, 0, 0, cv.BORDER_CONSTANT, value=[0, 0, 0])
                input_trimap = cv.copyMakeBorder(input_trimap, top_border, bottom_border, 0, 0, cv.BORDER_CONSTANT, value=[0, 0, 0])
                gt_alpha = cv.copyMakeBorder(gt_alpha, top_border, bottom_border, 0, 0, cv.BORDER_CONSTANT, value=[0, 0, 0])

        # Convert from BGR to RGB and store as PIL images
        rgb_input_img = cv.cvtColor(input_img, cv.COLOR_BGR2RGB)
        pil_input_img = transforms.ToPILImage()(rgb_input_img)

        display_rgb = transforms.ToTensor()(pil_input_img)

        inputs = torch.zeros((4, self.crop_size, self.crop_size), dtype=torch.float)
        inputs[0:3, :, :] = self.transformer(pil_input_img)
        inputs[3, :, :] = torch.from_numpy(input_trimap / 255.0)

        gts = torch.zeros((2, self.crop_size, self.crop_size), dtype=torch.float)
        gts[0, :, :] = torch.from_numpy(gt_alpha / 255.0)
        gt_trimap = np.zeros(gt_alpha.shape, np.float32)
        gt_trimap.fill(1.0)
        gt_trimap[gt_alpha == 0] = 0.0
        gt_trimap[gt_alpha == 255] = 2.0
        gts[1, :, :] = torch.from_numpy(gt_trimap)#out_gt_trimap)

        return display_rgb, inputs, gts


    def random_crop_pos(self, gt_trimap, crop_size=(320, 320)):
        crop_height, crop_width = crop_size
        y_indices, x_indices = np.where(gt_trimap == 128)
        num_unknowns = len(y_indices)
        x, y = 0, 0
        if num_unknowns > 0:
            ix = random.choice(range(num_unknowns))
            center_x = x_indices[ix]
            center_y = y_indices[ix]
            x = max(0, center_x - int(crop_width / 2))
            y = max(0, center_y - int(crop_height / 2))
        return x, y


    def do_crop(self, mat, x, y, crop_size):
        crop_height, crop_width = crop_size
        if len(mat.shape) == 2:
            ret = np.zeros((crop_height, crop_width), np.uint8)
        else:
            ret = np.zeros((crop_height, crop_width, 3), np.uint8)
        crop = mat[y:y + crop_height, x:x + crop_width]
        h, w = crop.shape[:2]
        ret[0:h, 0:w] = crop
        if crop_size != (self.crop_size, self.crop_size):
            ret = cv.resize(ret, dsize=(self.crop_size, self.crop_size), interpolation=cv.INTER_AREA)
        return ret


    def rotate_cv_image(self, image, angle=None, center=None, scale=1.0):
        (h, w) = image.shape[:2]

        if center is None:
            center = (w // 2, h // 2)
        if angle is None:
            angle = random.randint(-45, 45)

        M = cv.getRotationMatrix2D(center, angle, scale)
        rotated = cv.warpAffine(image, M, (w, h))
        return rotated
