"""
Robomimic BC-RNN training workspace
Reuse existing training framework, minimal changes
"""
import os
from typing import Optional
import torch
import hydra
from omegaconf import DictConfig, OmegaConf
import wandb
from tqdm import tqdm

from diffusion_policies.workspace.base_workspace import BaseWorkspace
from diffusion_policies.common.pytorch_util import dict_apply


class TrainRobomimicWorkspace(BaseWorkspace):
    """Robomimic BC-RNN training workspace"""

    include_keys = ['global_step', 'epoch']

    def __init__(self, cfg: DictConfig, output_dir: Optional[str] = None):
        super().__init__(cfg, output_dir=output_dir)

        # Create policy
        self.policy = hydra.utils.instantiate(cfg.policy)

        # Load dataset (direct import, not Hydra, to avoid numba issues)
        from diffusion_policies.dataset.multimodal_dataset_v2 import MultiModalDatasetV2
        self.dataset = MultiModalDatasetV2(
            zarr_path=cfg.dataset.zarr_path,
            horizon=cfg.dataset.horizon,
            pad_before=cfg.dataset.pad_before,
            pad_after=cfg.dataset.pad_after,
            seed=cfg.dataset.seed,
            val_ratio=cfg.dataset.val_ratio,
            max_train_episodes=cfg.dataset.get('max_train_episodes', None),
            max_val_episodes=cfg.dataset.get('max_val_episodes', None)
        )

        # Set normalizer
        normalizer = self.dataset.get_normalizer()
        self.policy.set_normalizer(normalizer)

        # Create dataloader
        self.train_dataloader = torch.utils.data.DataLoader(
            self.dataset,
            **cfg.dataloader
        )

        # Validation set (simplified: use same dataset)
        self.val_dataloader = torch.utils.data.DataLoader(
            self.dataset,
            **cfg.val_dataloader
        )

        # Optimizer
        self.optimizer = hydra.utils.instantiate(
            cfg.optimizer,
            params=self.policy.parameters()
        )

        # LR scheduler
        if cfg.training.lr_scheduler == 'cosine':
            self.lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                self.optimizer,
                T_max=cfg.training.num_epochs,
                eta_min=cfg.optimizer.lr * 0.01
            )
        else:
            self.lr_scheduler = None

        # Move to device
        self.device = torch.device(cfg.training.device)
        self.policy.to(self.device)  # Note: move in-place, don't reassign

        # Training state
        self.global_step = 0
        self.epoch = 0

        # W&B init
        if cfg.logging.mode == 'online':
            wandb.init(
                project=cfg.logging.project,
                name=cfg.logging.name,
                config=OmegaConf.to_container(cfg, resolve=True),
                tags=cfg.logging.tags,
                dir=output_dir
            )

        print(f"BC-RNN workspace initialized")
        print(f"   Train samples: {len(self.train_dataloader.dataset)}")
        print(f"   Batch size: {cfg.dataloader.batch_size}")
        print(f"   Total epochs: {cfg.training.num_epochs}")
        print(f"   Policy type: {type(self.policy)}")
        print(f"   Device: {self.device}")

    def run(self):
        """Run training loop"""
        cfg = self.cfg

        print("🚀 Start BC-RNN training...")

        best_val_loss = float('inf')

        for epoch in range(self.epoch, cfg.training.num_epochs):
            self.epoch = epoch

            # Train
            train_metrics = self.train_epoch()

            # Validate
            if (epoch + 1) % cfg.training.val_every == 0:
                val_metrics = self.val_epoch()

                # Log
                if cfg.logging.mode == 'online':
                    wandb.log({
                        'epoch': epoch,
                        **train_metrics,
                        **val_metrics,
                        'lr': self.optimizer.param_groups[0]['lr']
                    })

                print(f"Epoch {epoch+1}: train_loss={train_metrics['train_loss']:.4f}, val_loss={val_metrics['val_loss']:.4f}")

                # Save best model
                if val_metrics['val_loss'] < best_val_loss:
                    best_val_loss = val_metrics['val_loss']
                    self.save_checkpoint(
                        path=os.path.join(self.output_dir, 'best_model.ckpt'),
                        tag='best'
                    )
                    print(f"  Saved best model (val_loss={best_val_loss:.4f})")

            # Periodic save
            if (epoch + 1) % cfg.training.checkpoint_every == 0:
                self.save_checkpoint(
                    path=os.path.join(self.output_dir, f'epoch_{epoch+1}.ckpt')
                )

            # Update LR
            if self.lr_scheduler is not None:
                self.lr_scheduler.step()

        print("BC-RNN training completed!")

        if cfg.logging.mode == 'online':
            wandb.finish()

    def train_epoch(self):
        """Train one epoch"""
        self.policy.train()
        losses = []

        pbar = tqdm(self.train_dataloader, desc=f"Epoch {self.epoch+1} [Train]")
        for batch in pbar:
            # Move to device
            batch = dict_apply(
                batch,
                lambda x: x.to(self.device) if isinstance(x, torch.Tensor) else x
            )

            # Forward pass
            loss_dict = self.policy.compute_loss(batch)
            loss = loss_dict['loss']

            # Backward pass
            self.optimizer.zero_grad()
            loss.backward()

            # Gradient clipping
            if hasattr(self.cfg.training, 'max_grad_norm'):
                torch.nn.utils.clip_grad_norm_(
                    self.policy.parameters(),
                    self.cfg.training.max_grad_norm
                )

            self.optimizer.step()

            # Log
            losses.append(loss.item())
            pbar.set_postfix({'loss': f"{loss.item():.4f}"})

            self.global_step += 1

        return {'train_loss': sum(losses) / len(losses)}

    def val_epoch(self):
        """Validation"""
        self.policy.eval()
        losses = []

        with torch.no_grad():
            for batch in tqdm(self.val_dataloader, desc=f"Epoch {self.epoch+1} [Val]"):
                batch = dict_apply(
                    batch,
                    lambda x: x.to(self.device) if isinstance(x, torch.Tensor) else x
                )

                loss_dict = self.policy.compute_loss(batch)
                losses.append(loss_dict['loss'].item())

        return {'val_loss': sum(losses) / len(losses)}

    def save_checkpoint(self, path: Optional[str] = None, tag: str = 'latest'):
        """Save checkpoint"""
        if path is None:
            path = os.path.join(self.output_dir, f'{tag}.ckpt')

        torch.save({
            'epoch': self.epoch,
            'global_step': self.global_step,
            'model_state_dict': self.policy.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
        }, path)
