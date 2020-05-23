#/bin/bash

python main.py \
    --mode=train \
    --valid_portion=5 \
    --batch_size=24 \
    --epochs=120 \
    --lr=0.0001 \
    --decay_iters=51182 \
    --cuda \
    --gpu=1,2,3,6 \
    --write_log \
    --save_ckpt \
    # --resume=/data/datasets/im/AdaMatting/ckpt.tar
