from typing import Dict, Tuple, Union
import copy
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from diffusion_policies.model_dp_umi.vision.crop_randomizer import CropRandomizer
from diffusion_policies.model_dp_umi.common.module_attr_mixin import ModuleAttrMixin
from diffusion_policies.common.pytorch_util import dict_apply, replace_submodules


class ESPCrossAttention(nn.Module):
    """
    Lightweight cross attention between ESP A and ESP B
    Pre-LayerNorm design following modern Transformer best practices
    """
    def __init__(self, feature_dim: int, num_heads: int = 8, dropout: float = 0.1):
        super().__init__()
        
        self.feature_dim = feature_dim
        self.num_heads = num_heads
        
        # Pre-LayerNorm design (modern Transformer standard)
        self.norm_a = nn.LayerNorm(feature_dim)
        self.norm_b = nn.LayerNorm(feature_dim)

        # Bidirectional cross attention
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
        
        # Simplified FFN (optional)
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
            esp_a_feat: [batch_size, feature_dim]
            esp_b_feat: [batch_size, feature_dim]
        Returns:
            enhanced_esp_a, enhanced_esp_b: [batch_size, feature_dim]
        """
        # Add sequence dim
        esp_a_seq = esp_a_feat.unsqueeze(1)  # [B, 1, D]
        esp_b_seq = esp_b_feat.unsqueeze(1)  # [B, 1, D]
        
        # Cross Attention with Pre-LN and residual
        normed_a = self.norm_a(esp_a_seq)
        normed_b = self.norm_b(esp_b_seq)
        
        esp_a_cross, _ = self.cross_attn_a2b(normed_a, normed_b, normed_b)
        esp_b_cross, _ = self.cross_attn_b2a(normed_b, normed_a, normed_a)
        
        esp_a_enhanced = esp_a_seq + esp_a_cross
        esp_b_enhanced = esp_b_seq + esp_b_cross
        
        # FFN with Pre-LN and residual
        esp_a_enhanced = esp_a_enhanced + self.ffn_a(self.norm_a_2(esp_a_enhanced))
        esp_b_enhanced = esp_b_enhanced + self.ffn_b(self.norm_b_2(esp_b_enhanced))
        
        # Remove sequence dim
        return esp_a_enhanced.squeeze(1), esp_b_enhanced.squeeze(1)


class MultiImageObsEncoder(ModuleAttrMixin):
    def __init__(self,
            shape_meta: dict,
            rgb_model: Union[nn.Module, Dict[str,nn.Module]],
            resize_shape: Union[Tuple[int,int], Dict[str,tuple], None]=None,
            crop_shape: Union[Tuple[int,int], Dict[str,tuple], None]=None,
            random_crop: bool=True,
            # replace BatchNorm with GroupNorm
            use_group_norm: bool=False,
            # use single rgb model for all rgb inputs
            share_rgb_model: bool=False,
            # renormalize rgb input with imagenet normalization
            # assuming input in [0,1]
            imagenet_norm: bool=False,
            pretrained=False,
            # ESP Cross Attention parameters
            esp_feature_dim: int=512,
            esp_num_heads: int=8,
            esp_dropout: float=0.1
        ):
        """
        Assumes rgb input: B,C,H,W
        Assumes low_dim input: B,D
        """
        super().__init__()

        rgb_keys = list()
        low_dim_keys = list()
        key_model_map = nn.ModuleDict()
        key_transform_map = nn.ModuleDict()
        key_shape_map = dict()

        # handle sharing vision backbone
        if share_rgb_model:
            assert isinstance(rgb_model, nn.Module)
            key_model_map['rgb'] = rgb_model

        obs_shape_meta = shape_meta['obs']
        for key, attr in obs_shape_meta.items():
            shape = tuple(attr['shape'])
            type = attr.get('type', 'low_dim')
            key_shape_map[key] = shape
            if type == 'rgb':
                rgb_keys.append(key)
                # configure model for this key
                this_model = None
                if not share_rgb_model:
                    if isinstance(rgb_model, dict):
                        # have provided model for each key
                        this_model = rgb_model[key]
                    else:
                        assert isinstance(rgb_model, nn.Module)
                        # have a copy of the rgb model
                        this_model = copy.deepcopy(rgb_model)
                
                if this_model is not None:
                    if use_group_norm:
                        this_model = replace_submodules(
                            root_module=this_model,
                            predicate=lambda x: isinstance(x, nn.BatchNorm2d),
                            func=lambda x: nn.GroupNorm(
                                num_groups=x.num_features//16, 
                                num_channels=x.num_features)
                        )
                    key_model_map[key] = this_model
                
                # configure resize
                input_shape = shape
                this_resizer = nn.Identity()
                if resize_shape is not None:
                    if isinstance(resize_shape, dict):
                        h, w = resize_shape[key]
                    else:
                        h, w = resize_shape
                    this_resizer = torchvision.transforms.Resize(
                        size=(h,w)
                    )
                    input_shape = (shape[0],h,w)

                # configure randomizer
                this_randomizer = nn.Identity()
                if crop_shape is not None:
                    if isinstance(crop_shape, dict):
                        h, w = crop_shape[key]
                    else:
                        h, w = crop_shape
                    if random_crop:
                        this_randomizer = CropRandomizer(
                            input_shape=input_shape,
                            crop_height=h,
                            crop_width=w,
                            num_crops=1,
                            pos_enc=False
                        )
                    else:
                        this_normalizer = torchvision.transforms.CenterCrop(
                            size=(h,w)
                        )
                # configure normalizer
                this_normalizer = nn.Identity()
                if imagenet_norm:
                    this_normalizer = torchvision.transforms.Normalize(
                        mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
                
                this_transform = nn.Sequential(this_resizer, this_randomizer, this_normalizer)
                key_transform_map[key] = this_transform
            elif type == 'low_dim':
                low_dim_keys.append(key)
            else:
                raise RuntimeError(f"Unsupported obs type: {type}")
        rgb_keys = sorted(rgb_keys)
        low_dim_keys = sorted(low_dim_keys)

        self.shape_meta = shape_meta
        self.key_model_map = key_model_map
        self.key_transform_map = key_transform_map
        self.share_rgb_model = share_rgb_model
        self.rgb_keys = rgb_keys
        self.low_dim_keys = low_dim_keys
        self.key_shape_map = key_shape_map
        
        # ESP Cross Attention setup
        # Get the output dimension of the RGB model to determine feature dim
        if isinstance(rgb_model, nn.Module):
            # Try to get the feature dimension from the model
            if hasattr(rgb_model, 'fc'):
                esp_feature_dim = rgb_model.fc.out_features
            elif hasattr(rgb_model, 'classifier'):
                if isinstance(rgb_model.classifier, nn.Sequential):
                    esp_feature_dim = rgb_model.classifier[-1].out_features
                else:
                    esp_feature_dim = rgb_model.classifier.out_features
        
        self.esp_cross_attention = ESPCrossAttention(
            feature_dim=esp_feature_dim,
            num_heads=esp_num_heads,
            dropout=esp_dropout
        )

    def forward(self, obs_dict):
        batch_size = None
        features = list()
        # process rgb input
        if self.share_rgb_model:
            # pass all rgb obs to rgb model
            imgs = list()
            esp_a_idx = None
            esp_b_idx = None
            
            for i, key in enumerate(self.rgb_keys):
                img = obs_dict[key]
                if batch_size is None:
                    batch_size = img.shape[0]
                else:
                    assert batch_size == img.shape[0]
                assert img.shape[1:] == self.key_shape_map[key]
                img = self.key_transform_map[key](img)
                imgs.append(img)
                
                # Track ESP camera indices
                if 'esp_a' in key:
                    esp_a_idx = i
                elif 'esp_b' in key:
                    esp_b_idx = i
                        
            # (N*B,C,H,W)
            imgs = torch.cat(imgs, dim=0)
            # (N*B,D)
            feature = self.key_model_map['rgb'](imgs)
            # (N,B,D)
            feature = feature.reshape(-1,batch_size,*feature.shape[1:])
            
            # Apply Cross Attention if ESP cameras are present
            if esp_a_idx is not None and esp_b_idx is not None:
                esp_a_feat = feature[esp_a_idx]  # (B, D)
                esp_b_feat = feature[esp_b_idx]  # (B, D)
                
                enhanced_esp_a, enhanced_esp_b = self.esp_cross_attention(esp_a_feat, esp_b_feat)
                feature[esp_a_idx] = enhanced_esp_a
                feature[esp_b_idx] = enhanced_esp_b
            elif esp_a_idx is not None or esp_b_idx is not None:
                # V4 Ablation: Only one ESP camera available - skip cross attention
                pass
            
            # (B,N,D)
            feature = torch.moveaxis(feature,0,1)
            # (B,N*D)
            feature = feature.reshape(batch_size,-1)
            features.append(feature)
        else:
            # run each rgb obs to independent models
            esp_a_idx = None
            esp_b_idx = None
            esp_a_feat = None
            esp_b_feat = None
            
            for i, key in enumerate(self.rgb_keys):
                img = obs_dict[key]
                if batch_size is None:
                    batch_size = img.shape[0]
                else:
                    assert batch_size == img.shape[0]
                assert img.shape[1:] == self.key_shape_map[key]
                img = self.key_transform_map[key](img)
                feature = self.key_model_map[key](img)
                features.append(feature)
                
                # Track ESP camera features for cross attention
                if 'esp_a' in key:
                    esp_a_idx = i
                    esp_a_feat = feature
                elif 'esp_b' in key:
                    esp_b_idx = i
                    esp_b_feat = feature
            
            # Apply ESP Cross Attention if both ESP features are available
            if esp_a_feat is not None and esp_b_feat is not None:
                enhanced_esp_a, enhanced_esp_b = self.esp_cross_attention(esp_a_feat, esp_b_feat)
                features[esp_a_idx] = enhanced_esp_a
                features[esp_b_idx] = enhanced_esp_b
            elif esp_a_feat is not None or esp_b_feat is not None:
                # V4 Ablation: Only one ESP camera available - skip cross attention
                pass
        
        # process lowdim input
        for key in self.low_dim_keys:
            data = obs_dict[key]
            if batch_size is None:
                batch_size = data.shape[0]
            else:
                assert batch_size == data.shape[0]
            assert data.shape[1:] == self.key_shape_map[key]
            features.append(data)
        
        # concatenate all features
        result = torch.cat(features, dim=-1)
        return result
    
    @torch.no_grad()
    def output_shape(self):
        example_obs_dict = dict()
        obs_shape_meta = self.shape_meta['obs']
        batch_size = 1
        for key, attr in obs_shape_meta.items():
            shape = tuple(attr['shape'])
            this_obs = torch.zeros(
                (batch_size,) + shape, 
                dtype=self.dtype,
                device=self.device)
            example_obs_dict[key] = this_obs
        example_output = self.forward(example_obs_dict)
        output_shape = example_output.shape[1:]
        return output_shape
