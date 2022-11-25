# ugli.py

Python simplifier, minifier, and obfuscator

## Installation

    pip install ugli

## Usage

    ugli [options] <file>

## Comparison

We run comparisons against the following:

- pyminify - https://github.com/dflook/python-minifier
- pyminifier - https://github.com/liftoff/pyminifier
- mnfy - https://github.com/brettcannon/mnfy (does not work on Python >3.4)

To repeat our results, run the following to setup.

```
pip install python-minifier
pip install setuptools==57.5.0 && pip install pyminifier  # hack to get pyminifer to install
pip install mnfy  # if you're running python3.4
pip install uglipy  # ours
```

Then, run the following to get mini'd versions of the sample file.

```
mkdir -p out
pyminify --rename-globals --remove-literal-statements sample/test.py > out/pyminify.py
pyminifier --obfuscate sample/test.py > out/pyminifier.py
python -m mnfy sample/test.py > out/mnfy.py
python ugli.py sample/test.py > out/pyminiest.py
```

Then, run `ls -lh out`. You should see the following.

```
total 24
-rw-r--r--  1 alvinwan  staff   418B Nov 25 01:22 pyminiest.py
-rw-r--r--  1 alvinwan  staff   602B Nov 25 01:19 pyminifier.py
-rw-r--r--  1 alvinwan  staff   490B Nov 25 01:18 pyminify.py
```

By comparison, the original file size was 1355B; `uglipy` achieves the smallest file size, 15% smaller than `pyminify` and 30% smaller than `pyminifier`, improving the best possible obfuscated file size reduction from 64% to 69%.
