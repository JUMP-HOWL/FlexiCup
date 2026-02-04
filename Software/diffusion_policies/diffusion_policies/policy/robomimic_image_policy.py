"""
Robomimic Image Policy - BC-RNN implementation
Direct usage of robomimic library BC-RNN algorithm
"""
from typing import Dict
import torch
import torch.nn as nn
import torch.nn.functional as F
from diffusion_policies.model_dp_umi.common.normalizer import LinearNormalizer
from diffusion_policies.policy.base_image_policy import BaseImagePolicy
from diffusion_policies.common.pytorch_util import dict_apply

from robomimic.algo import algo_factory
from robomimic.algo.algo import PolicyAlgo
import robomimic.utils.obs_utils as ObsUtils
from diffusion_policies.common.robomimic_config_util import get_robomimic_config


class RobomimicImagePolicy(BaseImagePolicy):
    """
    Robomimic BC-RNN policy

    Standard BC-RNN implementation using robomimic library:
    - ResNet image encoder
    - LSTM for temporal processing
    - MLP for action output
    """

    def __init__(
        self,
        shape_meta: dict,
        # Robomimic algo config
        algo_name: str = 'bc_rnn',
        obs_type: str = 'image',
        task_name: str = 'square',
        dataset_type: str = 'ph',
        # Image config
        crop_shape: tuple = (76, 76),
        # RNN config
        rnn_horizon: int = 10,
        rnn_hidden_dim: int = 400,
        rnn_num_layers: int = 2,
    ):
        super().__init__()

        # Parse shape_meta
        action_shape = shape_meta['action']['shape']
        assert len(action_shape) == 1
        action_dim = action_shape[0]

        obs_shape_meta = shape_meta['obs']
        obs_config = {
            'low_dim': [],
            'rgb': [],
            'depth': [],
            'scan': []
        }

        obs_key_shapes = dict()
        for key, attr in obs_shape_meta.items():
            shape = attr['shape']
            type = attr.get('type', 'low_dim')

            # robomimic expects: image shape=[C,H,W], low_dim shape=[D]
            if type == 'rgb':
                # Image: [C, H, W] (keep full shape)
                obs_key_shapes[key] = list(shape)
                obs_config['rgb'].append(key)
            elif type == 'low_dim':
                # Low-dim: [D] (unchanged)
                obs_key_shapes[key] = list(shape)
                obs_config['low_dim'].append(key)
            else:
                raise RuntimeError(f"Unsupported obs type: {type}")

        print(f"BC-RNN: RGB cameras = {obs_config['rgb']}")
        print(f"BC-RNN: Lowdim state = {obs_config['low_dim']}")
        print(f"BC-RNN: Action dim = {action_dim}")
        print(f"BC-RNN: obs_key_shapes = {obs_key_shapes}")

        # Get robomimic config
        config = get_robomimic_config(
            algo_name=algo_name,
            hdf5_type=obs_type,
            task_name=task_name,
            dataset_type=dataset_type
        )

        with config.unlocked():
            # Set obs config
            config.observation.modalities.obs = obs_config

            # Set image crop
            if crop_shape is None:
                for key, modality in config.observation.encoder.items():
                    if modality.obs_randomizer_class == 'CropRandomizer':
                        modality['obs_randomizer_class'] = None
            else:
                ch, cw = crop_shape
                for key, modality in config.observation.encoder.items():
                    if modality.obs_randomizer_class == 'CropRandomizer':
                        modality.obs_randomizer_kwargs.crop_height = ch
                        modality.obs_randomizer_kwargs.crop_width = cw

            # Set RNN params
            if algo_name == 'bc_rnn':
                config.algo.rnn.horizon = rnn_horizon
                config.algo.rnn.hidden_dim = rnn_hidden_dim
                config.algo.rnn.rnn_num_layers = rnn_num_layers

        # Init ObsUtils
        ObsUtils.initialize_obs_utils_with_config(config)

        # Create robomimic model
        try:
            model: PolicyAlgo = algo_factory(
                algo_name=config.algo_name,
                config=config,
                obs_key_shapes=obs_key_shapes,
                ac_dim=action_dim,
                device='cpu',
            )
        except Exception as e:
            print(f"ERROR creating robomimic model: {e}")
            print(f"obs_key_shapes: {obs_key_shapes}")
            print(f"action_dim: {action_dim}")
            import traceback
            traceback.print_exc()
            raise

        self.model = model
        self.nets = model.nets
        self.normalizer = LinearNormalizer()
        self.config = config
        self.action_dim = action_dim

        # Count params
        num_params = sum(p.numel() for p in self.parameters() if p.requires_grad)
        print(f"BC-RNN: Total params = {num_params:,}")

    def to(self, *args, **kwargs):
        device, dtype, non_blocking, convert_to_format = torch._C._nn._parse_to(*args, **kwargs)
        if device is not None:
            self.model.device = device
        super().to(*args, **kwargs)

    def predict_action(self, obs_dict: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """
        Inference interface

        Args:
            obs_dict: Obs dict, each key shape (B, T, ...)

        Returns:
            Dict with 'action': (B, T, action_dim)
        """
        # Normalize
        nobs_dict = self.normalizer.normalize(obs_dict)

        # Robomimic needs (B, ...) input, take last timestep
        robomimic_obs_dict = dict_apply(nobs_dict, lambda x: x[:, -1, ...] if x.ndim > 2 else x)

        # Get action
        naction = self.model.get_action(robomimic_obs_dict)

        # Unnormalize
        action = self.normalizer['action'].unnormalize(naction)

        return {'action': action}

    def compute_loss(self, batch: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """
        Compute training loss

        Args:
            batch: Contains 'obs' and 'action'

        Returns:
            Loss dict
        """
        # Normalize obs and action
        nobs_dict = self.normalizer.normalize(batch['obs'])
        naction = self.normalizer['action'].normalize(batch['action'])

        # BC-RNN needs temporal dim! (B, T, ...)
        # Keep temporal dim, robomimic RNN handles it

        # Robomimic training - use process_batch_for_training
        # robomimic's train_on_batch auto backward, we need manual forward
        # Use nets["policy"] to compute loss directly
        from robomimic.algo.algo import PolicyAlgo

        # Manual forward to get loss with grad
        self.model.set_train()

        # Prepare batch
        input_batch = {
            'obs': nobs_dict,
            'actions': naction,
            'goal_obs': nobs_dict
        }

        # Forward pass - get predictions with grad
        predictions = self.model._forward_training(input_batch)

        # robomimic BC returns GMM dist params, extract means as action preds
        if isinstance(predictions, dict) and 'means' in predictions:
            pred_actions = predictions['means']  # GMM mean
        else:
            pred_actions = predictions

        # Compute loss (NLL for GMM or MSE for deterministic)
        if isinstance(predictions, dict) and 'log_probs' in predictions:
            # GMM: use negative log likelihood
            action_loss = -predictions['log_probs'].mean()
        else:
            # Deterministic: use MSE
            action_loss = F.mse_loss(pred_actions, naction)

        # Return loss with grad
        return {
            'loss': action_loss,
            'bc_loss': action_loss
        }

    def set_normalizer(self, normalizer: LinearNormalizer):
        """Set normalizer"""
        self.normalizer.load_state_dict(normalizer.state_dict())
