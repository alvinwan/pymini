import glob
import sys
from pathlib import Path
from uglipy.ugli import uglipy

def main():
    sources, modules = [], []
    for path in glob.iglob(sys.argv[1]):
        if not path.endswith('.py') or '.ugli.' in path:
            continue
        with open(path) as f:
            sources.append(f.read())
        modules.append(Path(path).stem)
    cleaned, modules = uglipy(sources, modules)
    for source, module in zip(cleaned, modules):
        with open(f'out/{module}.ugli.py', 'w') as f:
            f.write(source)


if __name__ == '__main__':
    main()