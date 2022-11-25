ugli.py

We run comparisons against the following:
- pyminify - https://github.com/dflook/python-minifier
- mnfy - https://github.com/brettcannon/mnfy (no longer maintained)
- pyminifier - https://github.com/liftoff/pyminifier

To repeat our results, run the following to setup.

```
pip install python-minifier
pip install setuptools==57.5.0 && pip install pyminifier
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

Here, `uglipy` achieves the smallest file size, 15% smaller than `pyminify` and 30% smaller than `pyminifier`.