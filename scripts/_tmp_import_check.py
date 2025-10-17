import importlib, sys
print('cwd0:', sys.path[0])
try:
    m = importlib.import_module('app')
    print('app module file:', getattr(m,'__file__',None))
    print('app package path:', getattr(m,'__path__',None))
except Exception as e:
    print('import error:', type(e).__name__, e)
