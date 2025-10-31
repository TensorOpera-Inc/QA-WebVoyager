#!/bin/bash
nohup python -u auto_eval.py \
    --api_key YOUR_OPENAI_API_KEY \
    --base_url YOUR_CUSTOM_BASE_URL \
    --process_dir ../results/examples \
    --max_attached_imgs 15 > evaluation.log &