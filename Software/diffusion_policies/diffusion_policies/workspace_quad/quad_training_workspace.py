"""
Four-Encoder Independent Diffusion Training Workspace V4 - Simplified (DemoGen Port)
================================================================

V4 simplified training workspace with:
- V4-specific layered learning rate strategy
- Feature balance monitoring and logging
- Individual encoder performance tracking
- Gate weight analysis
- V4 optimized training flow

Core features:
- Unified ResNet architecture training optimization
- Real-time feature balance monitoring
- Gate attention weight visualization
- Layered learning rate auto-adjustment
- DemoGen framework integration

Author: AI Assistant
Version: 4.0 (Simplified - DemoGen Port)
"""

import os
import copy
import torch
import numpy as np
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from omegaconf import OmegaConf
import hydra
from tqdm import tqdm

# DemoGen import path adaptation
try:
    import wandb
    # DemoGen imports
    from diffusion_policies.workspace.base_workspace import BaseWorkspace
    from diffusion_policies.policy_v4.diffusion_unet_four_independent_policy_v4_simplified import DiffusionUnetFourIndependentPolicyV4Simplified
    from diffusion_policies.dataset.metaworld_image_dataset import MetaworldImageDataset
    from diffusion_policies.common.checkpoint_util import TopKCheckpointManager
    from diffusion_policies.common.json_logger import JsonLogger
    from diffusion_policies.common.pytorch_util import dict_apply, optimizer_to
    from diffusion_policies.model_dp_umi.common.lr_scheduler import get_scheduler
    from diffusion_policies.model_dp_umi.diffusion.ema_model import EMAModel
    DEMOGEN_ENV = True
except ImportError:
    # Compatible original imports
    from diffusion_policy.workspace.base_workspace import BaseWorkspace
    from diffusion_policy.policy.diffusion_unet_four_independent_policy_v4_simplified import DiffusionUnetFourIndependentPolicyV4Simplified
    from diffusion_policy.dataset.valve_four_cross_dataset import ValveFourCrossDataset as DatasetClass
    from diffusion_policy.common.checkpoint_util import TopKCheckpointManager
    from diffusion_policy.common.json_logger import JsonLogger
    from diffusion_policy.common.pytorch_util import dict_apply, optimizer_to
    from diffusion_policy.model.common.lr_scheduler import get_scheduler
    from diffusion_policy.model.diffusion.ema_model import EMAModel
    DEMOGEN_ENV = False

class TrainDiffusionUnetFourIndependentWorkspaceV4Simplified(BaseWorkspace):
    """
    Four-Encoder Independent Diffusion Training Workspace V4 - Simplified (DemoGen Port)

    V4 simplified training workspace optimized for:
    1. V4-specific layered learning rate strategy
    2. Real-time feature balance monitoring
    3. Individual encoder performance tracking
    4. Gate weight analysis and visualization
    5. Unified ResNet architecture training optimization
    6. Seamless DemoGen framework integration
    """
    
    include_keys = ['global_step', 'epoch']
    
    def __init__(self, cfg: OmegaConf, output_dir=None):
        super().__init__(cfg, output_dir=output_dir)
        
        print("🚀 Init Four-Encoder Independent Diffusion Training Workspace V4 (Simplified - DemoGen Port)")
        print("="*70)

        # Init training state
        self.global_step = 0
        self.epoch = 0

        # Set random seed and device
        seed = cfg.training.seed
        torch.manual_seed(seed)
        device = torch.device(cfg.training.device)
        self.device = device

        # Create dataset - DemoGen adaptation
        print(f"📊 Load V4 training dataset (DemoGen adapted)...")
        if DEMOGEN_ENV:
            # Use DemoGen dataset
            self.dataset = hydra.utils.instantiate(cfg.task.dataset)
        else:
            # Use original dataset
            self.dataset = hydra.utils.instantiate(cfg.task.dataset)

        # Create dataloader
        dl_kwargs = dict(cfg.dataloader)
        
        # Safe config for single process
        if dl_kwargs.get('num_workers', 0) == 0:
            dl_kwargs['persistent_workers'] = False
            dl_kwargs['pin_memory'] = False
            dl_kwargs.pop('prefetch_factor', None)
            dl_kwargs.pop('timeout', None)
        
        try:
            self.train_dataloader = torch.utils.data.DataLoader(self.dataset, **dl_kwargs)
        except Exception as e:
            print(f"⚠️ DataLoader init failed, downgrade to single process (reason: {e})")
            safe_kwargs = dict(dl_kwargs)
            safe_kwargs.update({
                'num_workers': 0,
                'persistent_workers': False,
                'pin_memory': False
            })
            safe_kwargs.pop('prefetch_factor', None)
            safe_kwargs.pop('timeout', None)
            self.train_dataloader = torch.utils.data.DataLoader(self.dataset, **safe_kwargs)
        
        # Create model
        print(f"🔧 Create V4 simplified diffusion policy (DemoGen port)...")
        self.policy = hydra.utils.instantiate(cfg.policy)
        self.policy.set_normalizer(self.dataset.get_normalizer())
        self.policy.to(device)
        
        # Fix: re-enable gradients after moving to GPU
        for param in self.policy.parameters():
            param.requires_grad = True
        
        print(f"✅ V4 policy created (DemoGen version)")
        print(f"   - Policy type: {type(self.policy).__name__}")
        print(f"   - Device: {device}")
        print(f"   - Params: {sum(p.numel() for p in self.policy.parameters())/1e6:.1f}M")
        print(f"   - DemoGen integration: True")
        
        # Check model gradient status
        print(f"\n🔍 Check model gradient status after init:")
        grad_ok = self.policy.check_grad_status()
        if not grad_ok:
            print(f"⚠️ Found params without grad, fixing...")
            # Force enable all param gradients
            for param in self.policy.parameters():
                param.requires_grad = True
            print(f"✅ All param gradients enabled")
        
        # V4 layered optimizer setup
        print(f"🔧 Setup V4 layered LR optimizer...")
        self._setup_v4_optimizer(self.policy, cfg)

        # Final ensure all params have gradients enabled
        for param in self.policy.parameters():
            param.requires_grad = True
        
        # LR scheduler
        self.lr_scheduler = get_scheduler(
            name=cfg.lr_scheduler.name,
            optimizer=self.optimizer,
            num_warmup_steps=cfg.lr_scheduler.num_warmup_steps,
            num_training_steps=cfg.training.num_epochs * len(self.train_dataloader) if cfg.lr_scheduler.get('num_training_steps') is None else cfg.lr_scheduler.num_training_steps
        )
        
        # EMA model will be properly init before training starts
        self.ema_model: Optional[torch.nn.Module] = None
        self.ema: Optional[EMAModel] = None

        # Save components
        self.cfg = cfg

        # V4 performance monitoring components
        self._setup_v4_monitoring()

        # Create validation dataloader - DemoGen adaptation
        val_dataset = copy.deepcopy(self.dataset)
        if hasattr(val_dataset, 'set_val_mode'):
            val_dataset.set_val_mode()
        elif hasattr(val_dataset, 'get_validation_dataset'):
            val_dataset = val_dataset.get_validation_dataset()
            
        val_dl_kwargs = dict(cfg.val_dataloader) if hasattr(cfg, 'val_dataloader') else dict(cfg.dataloader)
        val_dl_kwargs['shuffle'] = False
        val_dl_kwargs['drop_last'] = False
        if val_dl_kwargs.get('num_workers', 0) > 0:
            val_dl_kwargs['num_workers'] = max(1, val_dl_kwargs['num_workers'] // 2)
        
        self.val_dataloader = torch.utils.data.DataLoader(val_dataset, **val_dl_kwargs)
        
        # Checkpoint manager
        self.topk_manager = TopKCheckpointManager(
            save_dir=os.path.join(self.output_dir, 'checkpoints'),
            **cfg.checkpoint.topk
        )
        
        # JSON logger
        self.json_logger = JsonLogger(
            os.path.join(self.output_dir, 'logs.json.txt')
        )
        
        # ==================== Training Acceleration Optimization ====================
        self._apply_acceleration_optimizations(cfg)

        print(f"✅ V4 training workspace init complete! (DemoGen port)")
        
    def _apply_acceleration_optimizations(self, cfg):
        """Apply training acceleration optimizations"""
        print(f"\n🚀 Apply training acceleration optimizations:")
        print("-" * 40)
        
        # 1. Mixed precision training
        if cfg.training.get('use_amp', True):
            print("✅ Enable mixed precision training (AMP)")
            self.scaler = torch.cuda.amp.GradScaler()
            self.use_amp = True
        else:
            self.scaler = None
            self.use_amp = False
        
        # 2. EMA model will be created after all init (delayed init)
        print("✅ EMA model will be delayed init to avoid param mismatch")
        self.ema_model = None
        self.ema = None
        
        # 3. PyTorch 2.0 compile optimization
        if cfg.training.get('compile_model', False):  # DemoGen default off to avoid compatibility issues
            try:
                print("✅ Apply PyTorch 2.0 compile optimization")
                self.policy = torch.compile(self.policy, mode='default')
            except Exception as e:
                print(f"⚠️ Compile optimization failed, continue with original model: {e}")
        
        # 4. Memory layout optimization
        if cfg.training.get('channels_last', True):
            print("✅ Enable channels_last memory layout optimization")
            self.policy = self.policy.to(memory_format=torch.channels_last)
            self.channels_last = True
        else:
            self.channels_last = False
        
        # 5. CUDA optimization settings
        if torch.cuda.is_available():
            print("✅ Enable CUDA optimization settings")
            torch.backends.cudnn.benchmark = True  # Auto select optimal conv algorithm
            torch.backends.cuda.matmul.allow_tf32 = True  # Allow TF32 (A100/RTX30 series)
            torch.backends.cudnn.allow_tf32 = True

        print(f"✅ Training acceleration optimization complete!")
        
    def _setup_v4_optimizer(self, policy, cfg):
        """Setup V4 layered LR optimizer"""

        # V4 layered param groups
        param_groups = []

        # Collect all params, avoid duplicates
        all_params = set()

        # Gate and attention layer params (higher LR for fast adaptation)
        attention_params = []
        attention_param_names = []
        for name, param in policy.named_parameters():
            if any(keyword in name for keyword in ['gate', 'transformer', 'attention']):
                if param not in all_params:
                    attention_params.append(param)
                    attention_param_names.append(name)
                    all_params.add(param)
        
        if attention_params:
            param_groups.append({
                'params': attention_params,
                'lr': cfg.learning_rate.attention_lr, 
                'name': 'attention'
            })
            print(f"   ⚡ Attention layer params: {len(attention_params)} groups, LR: {cfg.learning_rate.attention_lr}")

        # UNet diffusion model params (standard LR)
        unet_params = []
        for param in policy.model.parameters():
            if param not in all_params:
                unet_params.append(param)
                all_params.add(param)
        
        if unet_params:
            param_groups.append({
                'params': unet_params, 
                'lr': cfg.learning_rate.unet_lr,
                'name': 'unet'
            })
            print(f"   🎯 UNet model params: {len(unet_params)} groups, LR: {cfg.learning_rate.unet_lr}")

        # Obs encoder params (lower LR, uses pretrained weights)
        obs_encoder_params = []
        for param in policy.obs_encoder.parameters():
            if param not in all_params:
                obs_encoder_params.append(param)
                all_params.add(param)
        
        if obs_encoder_params:
            param_groups.append({
                'params': obs_encoder_params,
                'lr': cfg.learning_rate.obs_encoder_lr,
                'name': 'obs_encoder'
            })
            print(f"   📊 Obs encoder params: {len(obs_encoder_params)} groups, LR: {cfg.learning_rate.obs_encoder_lr}")

        # Create optimizer
        optimizer_kwargs = dict(cfg.optimizer)
        optimizer_kwargs.pop('_target_', None)
        self.optimizer = torch.optim.AdamW(
            param_groups,
            **optimizer_kwargs
        )
        
        print(f"✅ V4 layered optimizer setup complete, {len(param_groups)} param groups")

    def _setup_v4_monitoring(self):
        """Setup V4 performance monitoring components"""
        self.v4_metrics = {
            'feature_balance_history': [],
            'encoder_sensitivity_history': {},
            'gate_weight_history': {},
            'training_stability': []
        }
        print(f"📊 V4 performance monitoring components init complete")

    def run(self):
        """Run V4 training loop - DemoGen integration"""
        cfg = self.cfg
        
        # ===================== Log detailed config info =====================
        print(f"\n{'='*80}")
        print(f"🚀 Start V4 simplified training - DemoGen integration")
        print(f"{'='*80}")

        # Save config to file
        config_file = os.path.join(self.output_dir, 'training_config.yaml')
        with open(config_file, 'w') as f:
            OmegaConf.save(cfg, f)
        
        config_json_file = os.path.join(self.output_dir, 'training_config.json')
        with open(config_json_file, 'w') as f:
            json.dump(OmegaConf.to_container(cfg, resolve=True), f, indent=2, ensure_ascii=False)
        
        print(f"📋 Training config saved to:")
        print(f"   - YAML: {config_file}")
        print(f"   - JSON: {config_json_file}")

        # Detailed config info display
        print(f"\n📊 V4 training config details (DemoGen version):")
        print(f"   🎯 Model architecture:")
        print(f"      - Policy type: {cfg.policy._target_.split('.')[-1]}")
        print(f"      - Obs encoder: Four independent ResNet18 (V4 simplified)")
        print(f"      - Diffusion steps: {cfg.policy.noise_scheduler.num_train_timesteps}")
        print(f"      - UNet dims: {cfg.policy.down_dims}")
        print(f"      - DemoGen integration: True")

        print(f"   ⚙️ Training params:")
        print(f"      - Epochs: {cfg.training.num_epochs}")
        print(f"      - Batch size: {cfg.dataloader.batch_size}")
        print(f"      - LR strategy: Layered (encoder:{cfg.learning_rate.obs_encoder_lr}, UNet:{cfg.learning_rate.unet_lr}, attention:{cfg.learning_rate.attention_lr})")
        print(f"      - Optimizer: {cfg.optimizer._target_.split('.')[-1]}")
        print(f"      - Scheduler: {cfg.lr_scheduler.name}")
        print(f"      - Device: {self.device}")

        print(f"   📈 Monitoring config:")
        print(f"      - Val interval: Every {cfg.training.val_every} epochs")
        print(f"      - Save interval: Every {cfg.training.save_every} epochs")
        print(f"      - Feature balance monitor: Every {cfg.monitoring.feature_balance_log_freq} epochs")
        print(f"      - Encoder sensitivity monitor: Every {cfg.monitoring.encoder_sensitivity_log_freq} epochs")

        print(f"   💾 Dataset info:")
        total_samples = len(self.dataset)
        train_samples = int(total_samples * (1 - getattr(cfg.task.dataset, 'val_ratio', 0.1)))
        val_samples = total_samples - train_samples
        batches_per_epoch = len(self.train_dataloader)
        print(f"      - Total samples: {total_samples}")
        print(f"      - Training samples: {train_samples}")
        print(f"      - Validation samples: {val_samples}")
        print(f"      - Batches per epoch: {batches_per_epoch}")

        # ===================== Init wandb monitoring =====================
        if DEMOGEN_ENV:
            print(f"\n🔧 Init wandb monitoring...")

            # Create wandb dir
            wandb_dir = os.path.join(self.output_dir, 'wandb')
            os.makedirs(wandb_dir, exist_ok=True)
            
            # wandb config
            wandb_config = OmegaConf.to_container(cfg, resolve=True)
            wandb_config.update({
                'output_dir': self.output_dir,
                'total_parameters': sum(p.numel() for p in self.policy.parameters()),
                'trainable_parameters': sum(p.numel() for p in self.policy.parameters() if p.requires_grad),
                'model_size_mb': sum(p.numel() * p.element_size() for p in self.policy.parameters()) / 1024 / 1024,
                'dataset_size': total_samples,
                'training_samples': train_samples,
                'validation_samples': val_samples,
                'demogen_integration': True
            })
            
            # Init wandb
            wandb.init(
                project=cfg.logging.project,
                group=cfg.logging.group,
                name=f"v4_simplified_demogen_{datetime.now().strftime('%m%d_%H%M')}",
                config=wandb_config,
                dir=wandb_dir,
                mode=cfg.logging.mode,
                tags=["v4_simplified", "four_independent", "demogen_migration"]
            )
            
            print(f"✅ wandb monitoring started:")
            print(f"   - Project: {cfg.logging.project}")
            print(f"   - Group: {cfg.logging.group}")
            print(f"   - Run name: {wandb.run.name}")

        # ===================== Init EMA model =====================
        print(f"\n🔧 Properly init EMA model...")
        if cfg.training.get('use_ema', True):
            import copy
            # Create EMA model only after all model params are set
            print("✅ Create EMA model deep copy")
            self.ema_model = copy.deepcopy(self.policy)
            self.ema_model.eval()
            for param in self.ema_model.parameters():
                param.requires_grad = False
            
            # Apply same memory format as main model
            if hasattr(self, 'channels_last') and self.channels_last:
                self.ema_model = self.ema_model.to(memory_format=torch.channels_last)
                print("✅ EMA model applied channels_last memory format")

            print("✅ Create EMA manager")
            self.ema = EMAModel(
                model=self.ema_model,
                **cfg.ema
            )
            print(f"✅ EMA model init complete, params: {sum(p.numel() for p in self.ema_model.parameters())/1e6:.1f}M")

        # ===================== Training loop =====================
        print(f"\n🏃‍♂️ Start training loop...")

        # Training state
        best_val_loss = float('inf')
        patience_counter = 0
        total_batches = cfg.training.num_epochs * batches_per_epoch
        processed_batches = 0
        
        # Time tracking
        training_start_time = time.time()
        epoch_times = []

        # Main training loop
        with tqdm(total=cfg.training.num_epochs, desc="🎯 Training progress", position=0) as epoch_pbar:
            for epoch in range(cfg.training.num_epochs):
                epoch_start_time = time.time()
                
                # Update epoch progress bar description
                epoch_pbar.set_description(f"🎯 Epoch {epoch+1}/{cfg.training.num_epochs}")

                # Training phase
                train_metrics = self._train_epoch_enhanced(epoch, epoch_pbar)
                processed_batches += batches_per_epoch

                # Validation phase
                val_metrics = {}
                if (epoch + 1) % cfg.training.val_every == 0:
                    val_metrics = self._validate_epoch_enhanced(epoch)

                    # Early stopping check
                    if cfg.training.early_stopping.enabled:
                        if val_metrics['val_loss'] < best_val_loss - cfg.training.early_stopping.min_delta:
                            best_val_loss = val_metrics['val_loss']
                            patience_counter = 0
                        else:
                            patience_counter += 1
                            
                        if patience_counter >= cfg.training.early_stopping.patience:
                            print(f"\n🛑 Early stopping triggered at epoch {epoch+1}")
                            break

                # Calculate time estimation
                epoch_end_time = time.time()
                epoch_duration = epoch_end_time - epoch_start_time
                epoch_times.append(epoch_duration)

                # Estimate remaining time
                avg_epoch_time = np.mean(epoch_times[-10:])  # Use avg of last 10 epochs
                remaining_epochs = cfg.training.num_epochs - (epoch + 1)
                eta_seconds = remaining_epochs * avg_epoch_time
                eta = timedelta(seconds=int(eta_seconds))

                # Update progress bar info
                progress_info = {
                    'loss': f"{train_metrics['train_loss']:.4f}",
                    'ETA': str(eta),
                    'epoch_time': f"{epoch_duration:.1f}s"
                }
                
                if val_metrics:
                    progress_info['val_loss'] = f"{val_metrics['val_loss']:.4f}"
                
                epoch_pbar.set_postfix(progress_info)
                epoch_pbar.update(1)
                
                # Log to wandb
                if DEMOGEN_ENV:
                    wandb_metrics = {
                        'epoch': epoch + 1,
                        'epoch_time': epoch_duration,
                        'eta_hours': eta_seconds / 3600,
                        'progress': (epoch + 1) / cfg.training.num_epochs,
                        **train_metrics
                    }
                    if val_metrics:
                        wandb_metrics.update(val_metrics)
                    
                    wandb.log(wandb_metrics)

                # V4 feature monitoring
                if (epoch + 1) % cfg.monitoring.feature_balance_log_freq == 0:
                    self._log_v4_feature_balance(epoch)
                    
                if (epoch + 1) % cfg.monitoring.encoder_sensitivity_log_freq == 0:
                    self._log_v4_encoder_sensitivity(epoch)
                    
                if (epoch + 1) % cfg.monitoring.gate_weight_log_freq == 0:
                    self._log_v4_gate_weights(epoch)
                
                # Save checkpoint
                if (epoch + 1) % cfg.training.save_every == 0:
                    self._save_checkpoint_enhanced(epoch, train_metrics.get('train_loss', 0), val_metrics.get('val_loss'))

        # Training complete
        total_training_time = time.time() - training_start_time
        print(f"\n✅ V4 training complete! (DemoGen integration)")
        print(f"📊 Training statistics:")
        print(f"   - Total training time: {timedelta(seconds=int(total_training_time))}")
        print(f"   - Avg epoch time: {total_training_time/len(epoch_times):.1f}s")
        print(f"   - Best val loss: {best_val_loss:.4f}")

        # Log final stats to wandb
        if DEMOGEN_ENV:
            wandb.log({
                'training_completed': True,
                'total_training_time_hours': total_training_time / 3600,
                'avg_epoch_time': total_training_time / len(epoch_times),
                'best_val_loss': best_val_loss,
                'final_epoch': len(epoch_times),
                'demogen_integration': True
            })
            
            wandb.finish()
        
    def _train_epoch_enhanced(self, epoch, epoch_pbar):
        """Train one epoch - DemoGen enhanced"""
        self.policy.train()

        # Force ensure all params have gradients in train mode
        for param in self.policy.parameters():
            param.requires_grad = True
        
        total_loss = 0.0
        num_batches = 0
        batch_losses = []
        
        # Create batch progress bar
        with tqdm(
            enumerate(self.train_dataloader),
            total=len(self.train_dataloader),
            desc=f"    📚 Training batches", 
            leave=False,
            position=1
        ) as batch_pbar:
            
            for batch_idx, batch in batch_pbar:
                batch_start_time = time.time()
                
                # Move to device
                batch = dict_apply(batch, lambda x: x.to(self.device, non_blocking=True))

                # Forward pass - handle s_prev param (ESP B region dynamic gating)
                s_prev = batch.get('s_prev', None)

                # DemoGen data format adaptation: ensure image data properly normalized
                if 'obs' in batch:
                    for key in batch['obs']:
                        if key in ['main_img', 'wrist_img', 'd435', 'esp_a', 'esp_b_vis', 'esp_b_tac']:
                            # If dtype is uint8, convert to float32 and normalize
                            if batch['obs'][key].dtype == torch.uint8:
                                batch['obs'][key] = batch['obs'][key].float() / 255.0

                # Apply channels_last memory format optimization
                if hasattr(self, 'channels_last') and self.channels_last:
                    for key in batch.get('obs', {}):
                        if len(batch['obs'][key].shape) >= 4:  # Image data
                            batch['obs'][key] = batch['obs'][key].to(memory_format=torch.channels_last)

                # Mixed precision forward pass
                if hasattr(self, 'use_amp') and self.use_amp:
                    with torch.cuda.amp.autocast():
                        loss = self.policy.compute_loss(batch, s_prev=s_prev)
                else:
                    loss = self.policy.compute_loss(batch, s_prev=s_prev)
                
                # Check loss gradient status
                if not loss.requires_grad:
                    print(f"❌ Error: loss doesn't require grad requires_grad={loss.requires_grad}")
                    raise RuntimeError("Loss tensor doesn't have gradient enabled")

                # Gradient accumulation
                loss = loss / self.cfg.training.gradient_accumulation_steps

                # Mixed precision backward pass
                if hasattr(self, 'use_amp') and self.use_amp:
                    self.scaler.scale(loss).backward()
                else:
                    loss.backward()
                
                if (batch_idx + 1) % self.cfg.training.gradient_accumulation_steps == 0:
                    # Mixed precision gradient update
                    if hasattr(self, 'use_amp') and self.use_amp:
                        # Gradient clipping (mixed precision)
                        self.scaler.unscale_(self.optimizer)
                        grad_norm = torch.nn.utils.clip_grad_norm_(
                            self.policy.parameters(),
                            self.cfg.training.max_grad_norm
                        )
                        # Optimizer step
                        self.scaler.step(self.optimizer)
                        self.scaler.update()
                    else:
                        # Gradient clipping (normal precision)
                        grad_norm = torch.nn.utils.clip_grad_norm_(
                            self.policy.parameters(),
                            self.cfg.training.max_grad_norm
                        )
                        # Optimizer step
                        self.optimizer.step()

                    self.lr_scheduler.step()
                    self.optimizer.zero_grad()

                    # Update EMA model
                    if self.ema is not None:
                        self.ema.step(self.policy)
                else:
                    grad_norm = 0.0
                
                # Log loss
                batch_loss = loss.item() * self.cfg.training.gradient_accumulation_steps  # Restore original loss value
                total_loss += batch_loss
                num_batches += 1
                batch_losses.append(batch_loss)

                # Calculate batch processing time
                batch_time = time.time() - batch_start_time

                # Update batch progress bar
                batch_pbar.set_postfix({
                    'loss': f"{batch_loss:.4f}",
                    'avg_loss': f"{total_loss/num_batches:.4f}",
                    'grad_norm': f"{grad_norm:.2f}",
                    'time': f"{batch_time:.2f}s"
                })
                
                # Log detailed batch info to wandb
                if DEMOGEN_ENV and (batch_idx + 1) % (self.cfg.training.log_every * 5) == 0:  # Reduce log frequency
                    current_lr = self.lr_scheduler.get_last_lr()[0]
                    wandb.log({
                        'batch_loss': batch_loss,
                        'batch_avg_loss': total_loss / num_batches,
                        'learning_rate': current_lr,
                        'grad_norm': grad_norm,
                        'batch_time': batch_time,
                        'epoch': epoch + 1,
                        'global_step': epoch * len(self.train_dataloader) + batch_idx + 1
                    })
        
        avg_train_loss = total_loss / num_batches
        
        # Calculate training loss statistics
        loss_std = np.std(batch_losses[-100:]) if len(batch_losses) >= 100 else np.std(batch_losses)
        loss_min = min(batch_losses[-100:]) if len(batch_losses) >= 100 else min(batch_losses)
        loss_max = max(batch_losses[-100:]) if len(batch_losses) >= 100 else max(batch_losses)

        print(f"    📊 Training loss stats: avg={avg_train_loss:.4f}, std={loss_std:.4f}, range=[{loss_min:.4f}, {loss_max:.4f}]")
        
        return {
            'train_loss': avg_train_loss,
            'train_loss_std': loss_std,
            'train_loss_min': loss_min,
            'train_loss_max': loss_max,
            'learning_rate': self.lr_scheduler.get_last_lr()[0]
        }
    
    def _validate_epoch_enhanced(self, epoch):
        """Validate one epoch - DemoGen enhanced"""
        self.policy.eval()
        total_val_loss = 0.0
        num_batches = 0
        val_losses = []
        
        print(f"    🔍 Start validation...")

        with torch.no_grad():
            with tqdm(
                enumerate(self.val_dataloader),
                total=len(self.val_dataloader),
                desc=f"    🔍 Validation batches",
                leave=False,
                position=1
            ) as val_pbar:
                
                for batch_idx, batch in val_pbar:
                    batch = dict_apply(batch, lambda x: x.to(self.device, non_blocking=True))
                    s_prev = batch.get('s_prev', None)
                    
                    # DemoGen data format adaptation
                    if 'obs' in batch:
                        for key in batch['obs']:
                            if key in ['main_img', 'wrist_img', 'd435', 'esp_a', 'esp_b_vis', 'esp_b_tac']:
                                if batch['obs'][key].dtype == torch.uint8:
                                    batch['obs'][key] = batch['obs'][key].float() / 255.0
                    
                    loss = self.policy.compute_loss(batch, s_prev=s_prev)
                    
                    batch_loss = loss.item()
                    total_val_loss += batch_loss
                    num_batches += 1
                    val_losses.append(batch_loss)
                    
                    # Update validation progress bar
                    val_pbar.set_postfix({
                        'val_loss': f"{batch_loss:.4f}",
                        'avg_val_loss': f"{total_val_loss/num_batches:.4f}"
                    })
        
        avg_val_loss = total_val_loss / num_batches
        
        # Calculate validation loss statistics
        val_loss_std = np.std(val_losses)
        val_loss_min = min(val_losses)
        val_loss_max = max(val_losses)

        print(f"    📊 Validation loss stats: avg={avg_val_loss:.4f}, std={val_loss_std:.4f}, range=[{val_loss_min:.4f}, {val_loss_max:.4f}]")
        
        return {
            'val_loss': avg_val_loss,
            'val_loss_std': val_loss_std,
            'val_loss_min': val_loss_min,
            'val_loss_max': val_loss_max
        }
    
    def _log_v4_feature_balance(self, epoch):
        """Log V4 feature balance info"""
        self.policy.eval()
        with torch.no_grad():
            # Get one batch of data
            batch = next(iter(self.val_dataloader))
            batch = dict_apply(batch, lambda x: x.to(self.device, non_blocking=True))

            # Get feature balance stats
            balance_stats = self.policy.get_feature_balance_stats(batch['obs'])
            
            self.v4_metrics['feature_balance_history'].append({
                'epoch': epoch,
                **balance_stats
            })
            
            print(f"   📊 Feature balance ratio: {balance_stats['balance_ratio']:.2f}")

            # Log to wandb
            if DEMOGEN_ENV and wandb.run is not None:
                wandb.log({
                    'feature_balance_ratio': balance_stats['balance_ratio'],
                    'image_feature_norm': balance_stats['image_norm'],
                    'state_feature_norm': balance_stats['state_norm'],
                    'epoch': epoch
                })
    
    def _log_v4_encoder_sensitivity(self, epoch):
        """Log V4 individual encoder sensitivity"""
        print(f"   🔬 Analyze individual encoder sensitivity...")
        # Can integrate encoder_test_utils testing functionality here

    def _log_v4_gate_weights(self, epoch):
        """Log V4 gate weight distribution"""
        self.policy.eval()
        gate_weights = {}
        
        with torch.no_grad():
            # Collect gate layer weight stats
            for name, param in self.policy.obs_encoder.named_parameters():
                if 'gate' in name and 'weight' in name:
                    gate_weights[name] = {
                        'mean': param.mean().item(),
                        'std': param.std().item(),
                        'min': param.min().item(),
                        'max': param.max().item()
                    }
        
        if gate_weights and DEMOGEN_ENV and wandb.run is not None:
            for gate_name, stats in gate_weights.items():
                wandb.log({
                    f'gate_weights/{gate_name}_mean': stats['mean'],
                    f'gate_weights/{gate_name}_std': stats['std'],
                    'epoch': epoch
                })
    
    def _save_checkpoint_enhanced(self, epoch, train_loss, val_loss=None):
        """Save checkpoint - DemoGen enhanced"""
        # Ensure checkpoint dir exists
        checkpoint_dir = os.path.join(self.output_dir, 'checkpoints')
        os.makedirs(checkpoint_dir, exist_ok=True)

        # Create checkpoint filename
        if val_loss is not None:
            checkpoint_filename = f"epoch={epoch+1:04d}-train_loss={train_loss:.4f}-val_loss={val_loss:.4f}.ckpt"
        else:
            checkpoint_filename = f"epoch={epoch+1:04d}-train_loss={train_loss:.4f}.ckpt"
        
        checkpoint_path = os.path.join(checkpoint_dir, checkpoint_filename)
        
        # Save checkpoint
        checkpoint_data = {
            'epoch': epoch + 1,
            'model_state_dict': self.policy.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'lr_scheduler_state_dict': self.lr_scheduler.state_dict(),
            'train_loss': train_loss,
            'val_loss': val_loss,
            'config': OmegaConf.to_container(self.cfg, resolve=True),
            'v4_metrics': self.v4_metrics,
            'timestamp': datetime.now().isoformat(),
            'device': str(self.device),
            'total_parameters': sum(p.numel() for p in self.policy.parameters()),
            'trainable_parameters': sum(p.numel() for p in self.policy.parameters() if p.requires_grad),
            'demogen_integration': DEMOGEN_ENV
        }
        
        if hasattr(self, 'ema_model') and self.ema_model is not None:
            checkpoint_data['ema_model_state_dict'] = self.ema_model.state_dict()
        if hasattr(self, 'ema') and self.ema is not None:
            checkpoint_data['ema_decay'] = self.ema.decay
            checkpoint_data['ema_optimization_step'] = self.ema.optimization_step
        
        torch.save(checkpoint_data, checkpoint_path)

        # Also save latest checkpoint
        latest_checkpoint_path = os.path.join(checkpoint_dir, 'latest.ckpt')
        torch.save(checkpoint_data, latest_checkpoint_path)

        print(f"    💾 Checkpoint saved: {checkpoint_filename}")

        # Log to wandb
        if DEMOGEN_ENV and wandb.run is not None:
            wandb.log({
                'checkpoint_saved': True,
                'checkpoint_epoch': epoch + 1,
                'checkpoint_train_loss': train_loss,
                'checkpoint_val_loss': val_loss if val_loss is not None else 0
            })