import glob
from pathlib import Path
from pymini.pymini import minify
from argparse import ArgumentParser

def main():
    parser = ArgumentParser()
    parser.add_argument('path', help='Path to the file or directory to minify')
    parser.add_argument('--keep-module-names', action='store_true', help='Keep module names as they are. Useful for compressing libraries')
    parser.add_argument('--keep-global-variables', action='store_true', help='Keep global variables as they are. Useful for compressing libraries')
    parser.add_argument('--single-file', action='store_true', help='Concatenate all outputs into a single file')
    parser.add_argument('-o', '--output', help='Path to the output directory', default='./')
    args = parser.parse_args()

    sources, modules = [], []
    for path in glob.iglob(args.path):
        if not path.endswith('.py') or '.ugli.' in path:
            continue
        with open(path) as f:
            sources.append(f.read())
        modules.append(Path(path).stem)
    cleaned, modules = minify(
        sources, modules, keep_module_names=args.keep_module_names,
        keep_global_variables=args.keep_global_variables,
        output_single_file=args.single_file
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for source, module in zip(cleaned, modules):
        with open(output / f'{module}.py', 'w') as f:
            f.write(source)


if __name__ == '__main__':
    main()