from termcolor import cprint

def print_params(model):
    """
    Print the number of parameters in each part of the model.
    """
    # Dict to store param counts
    params_dict = {}

    all_num_param = sum(p.numel() for p in model.parameters())

    # Iterate all params
    for name, param in model.named_parameters():
        # Get part name (before first '.')
        part_name = name.split('.')[0]
        # Add to dict if not exists
        if part_name not in params_dict:
            params_dict[part_name] = 0
        # Add param count to part
        params_dict[part_name] += param.numel()

    # Print param counts
    cprint(f'----------------------------------', 'cyan')
    cprint(f'Class name: {model.__class__.__name__}', 'cyan')
    cprint(f'  Number of parameters: {all_num_param / 1e6:.4f}M', 'cyan')
    for part_name, num_params in params_dict.items():
        # print num (in M) and percentage
        cprint(f'   {part_name}: {num_params / 1e6:.4f}M ({num_params / all_num_param:.2%})', 'cyan')
    cprint(f'----------------------------------', 'cyan')