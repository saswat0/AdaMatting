#/bin/bash

python main.py \
    --mode=train \
    --valid_portion=5 \
    --batch_size=8 \
    --epochs=120 \
    --lr=0.0001 \
    --decay_iters=102363 \
    --cuda \
    --gpu=4,5 \
    --write_log \
    --save_ckpt #\
    #--resume=./ckpts/ckpt_best.pt
