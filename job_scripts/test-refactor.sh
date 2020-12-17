#!/bin/bash
#SBATCH -p gpu_short
#SBATCH -t 00:50:00
#SBATCH -c 12
#SBATCH --output /home/cbarkhof/slurm-logs/%j-slurm-log.out

module purge  # unload all that are active
module load 2019  # load 2019 software module for good python versions
module load Anaconda3  # load anacoda
module load CUDA/10.0.130  # load cuda
module load cuDNN/7.6.3-CUDA-10.0.130  # load cudnn
export LD_LIBRARY_PATH=/hpc/eb/Debian9/cuDNN/7.6.3-CUDA-10.0.130/lib64:$LD_LIBRARY_PATH

CONDA_PREFIX=$(conda info --base)
source $CONDA_PREFIX/etc/profile.d/conda.sh

conda deactivate # just to make sure other envs are not active
conda activate thesisenv # activate environment

python /home/cbarkhof/code-thesis/NewsVAE/train.py \
          --overwrite_args=False \
          \
          --run_name_prefix="TEST-REFACTOR-17DEC" \
          \
          --batch_size=3 \
          --max_train_steps_epoch_per_rank=50 \
          --max_valid_steps_epoch_per_rank=30 \
          --max_global_train_steps=150 \
          --accumulate_n_batches_grad=2 \
          \
          --lr=0.0001 \
          --lr_scheduler=False \
          --warmup_updates=0 \
          \
          --gradient_checkpointing=False \
          --use_amp=False \
          --n_gpus=2 \
          --n_nodes=1 \
          --ddp=True \
          \
          --logging=True \
          --log_every_n_steps=5 \
          --wandb_project="thesis" \
          \
          --tokenizer_name="roberta" \
          --dataset_name="cnn_dailymail" \
          --num_workers=4 \
          --debug_data=False \
          --debug_data_len=10 \
          --max_seq_len=64 \
          \
          --print_stats=True \
          --print_every_n_steps=1 \
          \
          --checkpoint=False \
          --checkpoint_every_n_steps=1000 \
          --load_from_checkpoint=False \
          --checkpoint_file="path/to/file.pth" \
          --continue_train_after_checkpoint_loading=False \
          \
          --seed=0 \
          --deterministic=True \
          \
          --hinge_loss_lambda=1 \
          --beta=0.5 \
          --KL_annealing=False \
          --KL_annealing_steps=1000 \
          --objective="beta-vae" \
          --mmd_lambda=1000 \
          \
          --latent_size=768 \
          --add_latent_via_memory=True \
          --add_latent_via_embeddings=True \
          --do_tie_weights=True \
          --code_dir_path="/home/cbarkhof/code-thesis/NewsVAE"
