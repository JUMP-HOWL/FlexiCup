from diffusion_policies.env_runner.base_runner import BaseRunner

class BlankRunner(BaseRunner):
    def __init__(self,
            output_dir,
            image_obs_only=False):
        super().__init__(output_dir)
        self.image_obs_only = image_obs_only
    
    def run(self, policy):
        return dict()
