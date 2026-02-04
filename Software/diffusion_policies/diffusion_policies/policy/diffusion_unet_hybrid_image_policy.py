from typing import Dict, Tuple, List
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange, reduce
from diffusers.schedulers.scheduling_ddpm import DDPMScheduler

from diffusion_policies.model_dp_umi.common.normalizer import LinearNormalizer
from diffusion_policies.policy.base_image_policy import BaseImagePolicy
from diffusion_policies.model_dp_umi.diffusion.conditional_unet1d import ConditionalUnet1D
from diffusion_policies.model_dp_umi.diffusion.mask_generator import LowdimMaskGenerator
from diffusion_policies.common.robomimic_config_util import get_robomimic_config
from diffusion_policies.common.model_util import print_params
from robomimic.algo import algo_factory
from robomimic.algo.algo import PolicyAlgo
import robomimic.utils.obs_utils as ObsUtils
import robomimic.models.base_nets as rmbn
import diffusion_policies.model_dp_umi.vision.crop_randomizer as dmvc
from diffusion_policies.common.pytorch_util import dict_apply, replace_submodules
from termcolor import cprint


class ESPCrossAttention(nn.Module):
    """
    Multi-head Cross Attention module for ESP-A and ESP-B feature fusion.
    Uses Pre-LayerNorm design following modern Transformer best practices.

    This module enables bidirectional information exchange between the
    peripheral zone (ESP-A) and central zone (ESP-B) cameras.
    """
    def __init__(self, feature_dim: int, num_heads: int = 8, dropout: float = 0.1):
        super().__init__()

        self.feature_dim = feature_dim
        self.num_heads = num_heads

        # Pre-LayerNorm design
        self.norm_a = nn.LayerNorm(feature_dim)
        self.norm_b = nn.LayerNorm(feature_dim)

        # Bidirectional Cross Attention
        self.cross_attn_a2b = nn.MultiheadAttention(
            embed_dim=feature_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True
        )

        self.cross_attn_b2a = nn.MultiheadAttention(
            embed_dim=feature_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True
        )

        # Feed-forward networks
        self.ffn_a = nn.Sequential(
            nn.Linear(feature_dim, feature_dim * 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(feature_dim * 2, feature_dim),
            nn.Dropout(dropout)
        )

        self.ffn_b = nn.Sequential(
            nn.Linear(feature_dim, feature_dim * 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(feature_dim * 2, feature_dim),
            nn.Dropout(dropout)
        )

        self.norm_a_2 = nn.LayerNorm(feature_dim)
        self.norm_b_2 = nn.LayerNorm(feature_dim)

    def forward(self, esp_a_feat: torch.Tensor, esp_b_feat: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            esp_a_feat: [batch_size, feature_dim] - peripheral zone features
            esp_b_feat: [batch_size, feature_dim] - central zone features
        Returns:
            enhanced_esp_a, enhanced_esp_b: [batch_size, feature_dim]
        """
        # Add sequence dimension for attention
        esp_a_seq = esp_a_feat.unsqueeze(1)  # [B, 1, D]
        esp_b_seq = esp_b_feat.unsqueeze(1)  # [B, 1, D]

        # Cross Attention with Pre-LN and residual connection
        normed_a = self.norm_a(esp_a_seq)
        normed_b = self.norm_b(esp_b_seq)

        esp_a_cross, _ = self.cross_attn_a2b(normed_a, normed_b, normed_b)
        esp_b_cross, _ = self.cross_attn_b2a(normed_b, normed_a, normed_a)

        esp_a_enhanced = esp_a_seq + esp_a_cross
        esp_b_enhanced = esp_b_seq + esp_b_cross

        # FFN with Pre-LN and residual connection
        esp_a_enhanced = esp_a_enhanced + self.ffn_a(self.norm_a_2(esp_a_enhanced))
        esp_b_enhanced = esp_b_enhanced + self.ffn_b(self.norm_b_2(esp_b_enhanced))

        # Remove sequence dimension
        return esp_a_enhanced.squeeze(1), esp_b_enhanced.squeeze(1)


class DiffusionUnetHybridImagePolicy(BaseImagePolicy):
    def __init__(self,
            shape_meta: dict,
            noise_scheduler: DDPMScheduler,
            horizon,
            n_action_steps,
            n_obs_steps,
            num_inference_steps=None,
            obs_as_global_cond=True,
            crop_shape=(76, 76),
            diffusion_step_embed_dim=256,
            down_dims=(256,512,1024),
            kernel_size=5,
            n_groups=8,
            condition_type='film',
            obs_encoder_group_norm=False,
            eval_fixed_crop=False,
            use_depth=False,
            use_depth_only=False,
            # ESP Cross Attention parameters
            enable_esp_cross_attention=True,
            esp_feature_dim=512,
            esp_num_heads=8,
            esp_dropout=0.1,
            # parameters passed to step
            **kwargs):
        super().__init__()

        self.use_depth = use_depth
        self.use_depth_only = use_depth_only
        self.enable_esp_cross_attention = enable_esp_cross_attention

        cprint(f"use_depth: {use_depth}, use_depth_only: {use_depth_only}", 'red')
        cprint(f"ESP Cross Attention: {enable_esp_cross_attention}, heads: {esp_num_heads}, dim: {esp_feature_dim}", 'cyan')

        # parse shape_meta
        action_shape = shape_meta['action']['shape']
        self.action_shape = action_shape
        if len(action_shape) == 1:
            action_dim = action_shape[0]
        elif len(action_shape) == 2: # use multiple hands
            action_dim = action_shape[0] * action_shape[1]
        else:
            raise NotImplementedError(f"Unsupported action shape {action_shape}")

        obs_shape_meta = shape_meta['obs']
        obs_config = {
            'low_dim': [],
            'rgb': [],
            'depth': [],
            'scan': []
        }

        if use_depth and not use_depth_only:
            obs_shape_meta['image']['shape'][0] = 4 # 3,H,W -> 4,H,W

        if use_depth and use_depth_only:
            obs_shape_meta['image']['shape'][0] = 1

        # Track RGB keys for cross attention
        rgb_keys = []
        obs_key_shapes = dict()
        for key, attr in obs_shape_meta.items():
            shape = attr['shape']
            obs_key_shapes[key] = list(shape)

            type = attr.get('type', 'low_dim')
            if type == 'rgb':
                obs_config['rgb'].append(key)
                rgb_keys.append(key)
            elif type == 'low_dim':
                obs_config['low_dim'].append(key)
            else:
                raise RuntimeError(f"Unsupported obs type: {type}")

        self.rgb_keys = sorted(rgb_keys)

        # Check if both ESP cameras are present for cross attention
        self.has_esp_a = any('esp_a' in k for k in rgb_keys)
        self.has_esp_b = any('esp_b' in k for k in rgb_keys)
        self.can_use_cross_attention = self.has_esp_a and self.has_esp_b and enable_esp_cross_attention

        if enable_esp_cross_attention:
            if self.can_use_cross_attention:
                cprint(f"✓ ESP Cross Attention ENABLED (both ESP-A and ESP-B present)", 'green')
            else:
                cprint(f"✗ ESP Cross Attention DISABLED (ESP-A: {self.has_esp_a}, ESP-B: {self.has_esp_b})", 'yellow')

        # get raw robomimic config
        config = get_robomimic_config(
            algo_name='bc_rnn',
            hdf5_type='image',
            task_name='square',
            dataset_type='ph')

        with config.unlocked():
            # set config with shape_meta
            config.observation.modalities.obs = obs_config

            if crop_shape is None:
                for key, modality in config.observation.encoder.items():
                    if modality.obs_randomizer_class == 'CropRandomizer':
                        modality['obs_randomizer_class'] = None
            else:
                # set random crop parameter
                ch, cw = crop_shape
                for key, modality in config.observation.encoder.items():
                    if modality.obs_randomizer_class == 'CropRandomizer':
                        modality.obs_randomizer_kwargs.crop_height = ch
                        modality.obs_randomizer_kwargs.crop_width = cw

        # init global state
        ObsUtils.initialize_obs_utils_with_config(config)

        # load model
        policy: PolicyAlgo = algo_factory(
                algo_name=config.algo_name,
                config=config,
                obs_key_shapes=obs_key_shapes,
                ac_dim=action_dim,
                device='cpu',
            )

        obs_encoder = policy.nets['policy'].nets['encoder'].nets['obs']

        if obs_encoder_group_norm:
            # replace batch norm with group norm
            replace_submodules(
                root_module=obs_encoder,
                predicate=lambda x: isinstance(x, nn.BatchNorm2d),
                func=lambda x: nn.GroupNorm(
                    num_groups=x.num_features//16,
                    num_channels=x.num_features)
            )

        if eval_fixed_crop:
            replace_submodules(
                root_module=obs_encoder,
                predicate=lambda x: isinstance(x, rmbn.CropRandomizer),
                func=lambda x: dmvc.CropRandomizer(
                    input_shape=x.input_shape,
                    crop_height=x.crop_height,
                    crop_width=x.crop_width,
                    num_crops=x.num_crops,
                    pos_enc=x.pos_enc
                )
            )

        # Get per-camera feature dimension from encoder
        # Each RGB camera outputs esp_feature_dim (default 512) features
        self.per_camera_feature_dim = esp_feature_dim

        # Create ESP Cross Attention module if enabled
        self.esp_cross_attention = None
        if self.can_use_cross_attention:
            self.esp_cross_attention = ESPCrossAttention(
                feature_dim=esp_feature_dim,
                num_heads=esp_num_heads,
                dropout=esp_dropout
            )
            cprint(f"Created ESPCrossAttention module: dim={esp_feature_dim}, heads={esp_num_heads}", 'green')

        # create diffusion model
        obs_feature_dim = obs_encoder.output_shape()[0]

        input_dim = action_dim + obs_feature_dim
        global_cond_dim = None
        if obs_as_global_cond:
            input_dim = action_dim
            global_cond_dim = obs_feature_dim * n_obs_steps

        model = ConditionalUnet1D(
            input_dim=input_dim,
            local_cond_dim=None,
            global_cond_dim=global_cond_dim,
            diffusion_step_embed_dim=diffusion_step_embed_dim,
            down_dims=down_dims,
            kernel_size=kernel_size,
            n_groups=n_groups,
            cond_predict_scale=True
        )

        self.obs_encoder = obs_encoder
        self.model = model
        self.noise_scheduler = noise_scheduler
        self.mask_generator = LowdimMaskGenerator(
            action_dim=action_dim,
            obs_dim=0 if obs_as_global_cond else obs_feature_dim,
            max_n_obs_steps=n_obs_steps,
            fix_obs_steps=True,
            action_visible=False
        )
        self.normalizer = LinearNormalizer()
        self.horizon = horizon
        self.obs_feature_dim = obs_feature_dim
        self.action_dim = action_dim
        self.n_action_steps = n_action_steps
        self.n_obs_steps = n_obs_steps
        self.obs_as_global_cond = obs_as_global_cond

        # Store kwargs, excluding ESP params that are already processed
        excluded_params = ['enable_esp_cross_attention', 'esp_feature_dim', 'esp_num_heads', 'esp_dropout']
        self.kwargs = {k: v for k, v in kwargs.items()
                       if not (k.startswith('esp_') or k in excluded_params)}

        if num_inference_steps is None:
            num_inference_steps = noise_scheduler.config.num_train_timesteps
        self.num_inference_steps = num_inference_steps

        print_params(self)

    def _encode_obs_with_cross_attention(self, obs_dict: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Encode observations with optional ESP Cross Attention.

        If both ESP-A and ESP-B cameras are present and cross attention is enabled,
        apply bidirectional attention between their features before concatenation.
        """
        # Get the obs_nets from encoder to access per-camera networks
        obs_nets = self.obs_encoder.obs_nets
        obs_randomizers = self.obs_encoder.obs_randomizers

        features = []
        esp_a_feat = None
        esp_b_feat = None
        esp_a_idx = None
        esp_b_idx = None

        # Process each observation key
        sorted_keys = sorted(obs_dict.keys())
        for idx, key in enumerate(sorted_keys):
            obs = obs_dict[key]

            # Check if this is an RGB observation with a network
            if key in obs_nets:
                # Apply randomizer if exists
                if key in obs_randomizers and obs_randomizers[key] is not None:
                    obs = obs_randomizers[key].forward_in(obs)

                # Get features from the network
                feat = obs_nets[key](obs)

                # Track ESP camera features for cross attention
                if 'esp_a' in key:
                    esp_a_feat = feat
                    esp_a_idx = len(features)
                elif 'esp_b' in key:
                    esp_b_feat = feat
                    esp_b_idx = len(features)

                features.append(feat)
            else:
                # Low-dim observation, just flatten
                features.append(obs.flatten(start_dim=1))

        # Apply Cross Attention if enabled and both ESP features are available
        if self.esp_cross_attention is not None and esp_a_feat is not None and esp_b_feat is not None:
            enhanced_a, enhanced_b = self.esp_cross_attention(esp_a_feat, esp_b_feat)
            features[esp_a_idx] = enhanced_a
            features[esp_b_idx] = enhanced_b

        # Concatenate all features
        return torch.cat(features, dim=-1)

    # ========= inference  ============
    def conditional_sample(self,
            condition_data, condition_mask,
            local_cond=None, global_cond=None,
            generator=None,
            # keyword arguments to scheduler.step
            **kwargs
            ):
        model = self.model
        scheduler = self.noise_scheduler

        trajectory = torch.randn(
            size=condition_data.shape,
            dtype=condition_data.dtype,
            device=condition_data.device,
            generator=generator)

        # set step values
        scheduler.set_timesteps(self.num_inference_steps)

        for t in scheduler.timesteps:
            # 1. apply conditioning
            trajectory[condition_mask] = condition_data[condition_mask]

            # 2. predict model output
            model_output = model(trajectory, t,
                local_cond=local_cond, global_cond=global_cond)

            # 3. compute previous image: x_t -> x_t-1
            trajectory = scheduler.step(
                model_output, t, trajectory,
                generator=generator,
                **kwargs
                ).prev_sample

        # finally make sure conditioning is enforced
        trajectory[condition_mask] = condition_data[condition_mask]

        return trajectory


    def predict_action(self, obs_dict: Dict[str, torch.Tensor], placeholder=None) -> Dict[str, torch.Tensor]:
        """
        obs_dict: must include "obs" key
        result: must include "action" key
        """
        # normalize input
        nobs = self.normalizer.normalize(obs_dict)
        if self.use_depth and not self.use_depth_only:
            nobs['image'] = torch.cat([nobs['image'], nobs['depth'].unsqueeze(-3)], dim=-3)
        if self.use_depth and self.use_depth_only:
            nobs['image'] = nobs['depth'].unsqueeze(-3)
        value = next(iter(nobs.values()))
        B, To = value.shape[:2]
        T = self.horizon
        Da = self.action_dim
        Do = self.obs_feature_dim
        To = self.n_obs_steps

        # build input
        device = self.device
        dtype = self.dtype

        # handle different ways of passing observation
        local_cond = None
        global_cond = None
        if self.obs_as_global_cond:
            # condition through global feature
            this_nobs = dict_apply(nobs, lambda x: x[:,:To,...].reshape(-1,*x.shape[2:]))

            # Use custom encoding with cross attention if enabled
            if self.can_use_cross_attention:
                nobs_features = self._encode_obs_with_cross_attention(this_nobs)
            else:
                nobs_features = self.obs_encoder(this_nobs)

            # reshape back to B, Do
            global_cond = nobs_features.reshape(B, -1)
            # empty data for action
            cond_data = torch.zeros(size=(B, T, Da), device=device, dtype=dtype)
            cond_mask = torch.zeros_like(cond_data, dtype=torch.bool)
        else:
            # condition through impainting
            this_nobs = dict_apply(nobs, lambda x: x[:,:To,...].reshape(-1,*x.shape[2:]))

            if self.can_use_cross_attention:
                nobs_features = self._encode_obs_with_cross_attention(this_nobs)
            else:
                nobs_features = self.obs_encoder(this_nobs)

            # reshape back to B, T, Do
            nobs_features = nobs_features.reshape(B, To, -1)
            cond_data = torch.zeros(size=(B, T, Da+Do), device=device, dtype=dtype)
            cond_mask = torch.zeros_like(cond_data, dtype=torch.bool)
            cond_data[:,:To,Da:] = nobs_features
            cond_mask[:,:To,Da:] = True

        # run sampling
        nsample = self.conditional_sample(
            cond_data,
            cond_mask,
            local_cond=local_cond,
            global_cond=global_cond,
            **self.kwargs)

        # unnormalize prediction
        naction_pred = nsample[...,:Da]
        action_pred = self.normalizer['action'].unnormalize(naction_pred)

        # get action
        start = To - 1
        end = start + self.n_action_steps
        action = action_pred[:,start:end]

        result = {
            'action': action,
            'action_pred': action_pred
        }
        return result

    # ========= training  ============
    def set_normalizer(self, normalizer: LinearNormalizer):
        self.normalizer.load_state_dict(normalizer.state_dict())

    def compute_loss(self, batch):
        # normalize input
        assert 'valid_mask' not in batch
        nobs = self.normalizer.normalize(batch['obs'])
        if self.use_depth and not self.use_depth_only:
            nobs['image'] = torch.cat([nobs['image'], nobs['depth'].unsqueeze(-3)], dim=-3)
        if self.use_depth and self.use_depth_only:
            nobs['image'] = nobs['depth'].unsqueeze(-3)
        nactions = self.normalizer['action'].normalize(batch['action'])
        batch_size = nactions.shape[0]
        horizon = nactions.shape[1]

        # handle different ways of passing observation
        local_cond = None
        global_cond = None
        trajectory = nactions
        cond_data = trajectory
        if self.obs_as_global_cond:
            # reshape B, T, ... to B*T
            this_nobs = dict_apply(nobs,
                lambda x: x[:,:self.n_obs_steps,...].reshape(-1,*x.shape[2:]))

            # Use custom encoding with cross attention if enabled
            if self.can_use_cross_attention:
                nobs_features = self._encode_obs_with_cross_attention(this_nobs)
            else:
                nobs_features = self.obs_encoder(this_nobs)

            # reshape back to B, Do
            global_cond = nobs_features.reshape(batch_size, -1)
        else:
            # reshape B, T, ... to B*T
            this_nobs = dict_apply(nobs, lambda x: x.reshape(-1, *x.shape[2:]))

            if self.can_use_cross_attention:
                nobs_features = self._encode_obs_with_cross_attention(this_nobs)
            else:
                nobs_features = self.obs_encoder(this_nobs)

            # reshape back to B, T, Do
            nobs_features = nobs_features.reshape(batch_size, horizon, -1)
            cond_data = torch.cat([nactions, nobs_features], dim=-1)
            trajectory = cond_data.detach()

        # generate impainting mask
        condition_mask = self.mask_generator(trajectory.shape)

        # Sample noise that we'll add to the images
        noise = torch.randn(trajectory.shape, device=trajectory.device)
        bsz = trajectory.shape[0]
        # Sample a random timestep for each image
        timesteps = torch.randint(
            0, self.noise_scheduler.config.num_train_timesteps,
            (bsz,), device=trajectory.device
        ).long()
        # Add noise to the clean images according to the noise magnitude at each timestep
        # (this is the forward diffusion process)
        noisy_trajectory = self.noise_scheduler.add_noise(
            trajectory, noise, timesteps)

        # compute loss mask
        loss_mask = ~condition_mask

        # apply conditioning
        noisy_trajectory[condition_mask] = cond_data[condition_mask]

        # Predict the noise residual
        pred = self.model(noisy_trajectory, timesteps,
            local_cond=local_cond, global_cond=global_cond)

        pred_type = self.noise_scheduler.config.prediction_type
        if pred_type == 'epsilon':
            target = noise
        elif pred_type == 'sample':
            target = trajectory
        else:
            raise ValueError(f"Unsupported prediction type {pred_type}")

        loss = F.mse_loss(pred, target, reduction='none')
        loss = loss * loss_mask.type(loss.dtype)
        loss = reduce(loss, 'b ... -> b (...)', 'mean')
        loss = loss.mean()
        return loss

    def forward(self, batch):
        return self.compute_loss(batch)
