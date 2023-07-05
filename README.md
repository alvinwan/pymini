# ugli.py

Python simplifier, minifier, and obfuscator. Built to operate on entire libraries, persisting and supporting obfuscation across files.

## Installation

    pip install ugli

## Usage

    uglipy [options] <file>

To uglify a library, use the following options to preserve
your ability to import and use the library's publicly-facing
utilities.

    uglipy --keep-module-names --keep-global-variables <file>

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

Then, run the following to get mini'd versions of the sample file `sample/test.py`, which comes from `pyminifer`'s repository.

```
mkdir -p out
pyminify --rename-globals --remove-literal-statements sample/test.py > out/pyminify.py
pyminifier --obfuscate sample/test.py > out/pyminifier.py
python -m mnfy sample/test.py > out/mnfy.py
uglipy sample/test.py > out/pyminiest.py
```

Then, run `ls -lh out`. You should see the following.

```
total 24
-rw-r--r--  1 alvinwan  staff   414B Nov 25 01:22 pyminiest.py
-rw-r--r--  1 alvinwan  staff   602B Nov 25 01:19 pyminifier.py
-rw-r--r--  1 alvinwan  staff   490B Nov 25 01:18 pyminify.py
```

By comparison, the original file size was 1355B; `uglipy` achieves the smallest file size, 16% smaller than `pyminify` and 30% smaller than `pyminifier`, improving the best possible obfuscated file size reduction from 64% to 71%. We can also test against `test2.py`, which comes from `pyminify`'s repository.

```
-rw-r--r--  1 alvinwan  staff   914B Nov 25 02:09 pyminiest.py
-rw-r--r--  1 alvinwan  staff   1.4K Nov 25 01:32 pyminifier.py
-rw-r--r--  1 alvinwan  staff   977B Nov 25 01:32 pyminify.py
```

By comparison, the original file size was 1990B. `uglipy`'s file size is 6% smaller than `pyminify` and 34% smaller than `pyminifier`, improving the best possible obfuscated file size reduction from 51% to 54%.

## Develop

Run tests using the following, from the root directory

```
py.test --doctest-modules
```