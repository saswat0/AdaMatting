#/bin/bash

python main.py \
    --mode=train \
    --valid_portion=5 \
    --batch_size=8 \
    --epochs=120 \
    --lr=0.0001 \
    --cuda \
    --gpu=2,7 \
    --write_log \
    --save_ckpt \
    # --resume \
    --ckpt_path=./ckpts/ckpt_005_-0.2545_best.tar

    #--resume=model/stage1/ckpt_e1.pth \
