import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
from diffusion_policies.workspace.base_workspace import BaseWorkspace
import pathlib
from omegaconf import OmegaConf
import hydra
from termcolor import cprint

import sys
# use line-buffering for both stdout and stderr
sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)
sys.stderr = open(sys.stderr.fileno(), mode='w', buffering=1)

os.environ['WANDB_SILENT'] = "True"

# allows arbitrary python code execution in configs using the ${eval:''} resolver
OmegaConf.register_new_resolver("eval", eval, replace=True)


@hydra.main(
    version_base=None,
    config_path=str(pathlib.Path(__file__).parent.joinpath(
        'diffusion_policies', 'config'))
)
def main(cfg: OmegaConf):
    """
    Multimodal diffusion policy training main function
    """
    cprint("🚀 Starting multimodal robot diffusion policy training", "cyan")
    cprint(f"📝 Config: {cfg._target_}", "blue")

    # resolve immediately so all the ${now:} resolvers
    # will use the same time.
    OmegaConf.resolve(cfg)

    # Print key config info
    cprint(f"🎯 Task: {cfg.task_name}", "green")
    cprint(f"📊 Batch size: {cfg.dataloader.batch_size}", "green")
    cprint(f"🔄 Epochs: {cfg.training.num_epochs}", "green")
    cprint(f"📐 Obs steps: {cfg.n_obs_steps}", "green")
    cprint(f"🎬 Action steps: {cfg.n_action_steps}", "green")

    # Initialize workspace and start training
    cls = hydra.utils.get_class(cfg._target_)
    workspace: BaseWorkspace = cls(cfg)

    cprint("✅ Workspace initialized, starting training...", "cyan")
    workspace.run()


if __name__ == "__main__":
    main()