notes
problems with pyminifier
- obfuscation is wrong. called `.test` after renaming
- only obfuscates in global scope
- does it handle case where one-letter all exhausted?
problems with pyminify
- only obfuscates in global scope
- does not obfuscate method names like pyminifer does (which it does incorrectly)
    - try case with `getattr(...)` then can't trace class with AST

baselines:
- pyminify - https://github.com/dflook/python-minifier
- mnfy - https://github.com/brettcannon/mnfy (no longer maintained)
- pyminifier - https://github.com/liftoff/pyminifier

```
pip install python-minifier
pyminify --rename-globals --remove-literal-statements test.py > pyminify.py

pip install pyminifier
pyminifier --obfuscate test.py > pyminifier.py
```

more optimizations:
- respect `__all__`?
- simplify:
    - change `w = ...; return w` to `return ...`
- minify:
    - can push all onto one line using `;`
- obfucsate:
    - use 0 instead of pass
    - obfuscate in local scope (watch out for collisions with global scope)
    - only run for variables used multiple times
        - or calculate when using extra line to redefine would be a net savings
        - replace `self` too


outline:
- need `globals()` and `locals()` per scope to ensure new variable names dont collide
- need AST? maybe. so that we can sub in new names for variables