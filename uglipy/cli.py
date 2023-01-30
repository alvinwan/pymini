import glob
import sys
from pathlib import Path
from uglipy.ugli import uglipy
from argparse import ArgumentParser

def main():
    parser = ArgumentParser()
    parser.add_argument('path', help='Path to the file or directory to uglipy')
    parser.add_argument('-o', '--output', help='Path to the output directory', default='./')
    args = parser.parse_args()

    sources, modules = [], []
    for path in glob.iglob(args.path):
        if not path.endswith('.py') or '.ugli.' in path:
            continue
        with open(path) as f:
            sources.append(f.read())
        modules.append(Path(path).stem)
    cleaned, modules = uglipy(sources, modules)
    for source, module in zip(cleaned, modules):
        with open(Path(args.output) / f'{module}.ugli.py', 'w') as f:
            f.write(source)


if __name__ == '__main__':
    main()