pymini

We run comparisons against the following:
- pyminify - https://github.com/dflook/python-minifier
- mnfy - https://github.com/brettcannon/mnfy (no longer maintained)
- pyminifier - https://github.com/liftoff/pyminifier

To repeat our results, run the following to setup.

```
pip install python-minifier
pip install pyminifer
pip install pyminiest  # ours
```

Then, run the following to get mini'd versions of the sample file.

```
mkdir -p out
pyminify --rename-globals --remove-literal-statements sample/test.py > out/pyminify.py
pyminifier --obfuscate sample/test.py > out/pyminifier.py
mnfy sample/test.py > out/mnfy.py
pyminiest sample/test.py > out/pyminiest.py
```

Then, run `ls -lh out`. You should see the following.