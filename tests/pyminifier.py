#!/usr/bin/env python
T=ImportError
q=print
m=False
O=object
try:
 import demiurgic
except T:
 q("Warning: You're not demiurgic. Actually, I think that's normal.")
try:
 import mystificate
except T:
 q("Warning: Dark voodoo may be unreliable.")
Q=m
class U(O):
 def __init__(self,*args,**kwargs):
  pass
 def B(self,dactyl):
  G=demiurgic.palpitation(dactyl)
  w=mystificate.dark_voodoo(G)
  return w
 def k(self,whatever):
  q(whatever)
if __name__=="__main__":
 q("Forming...")
 f=U("epicaricacy","perseverate")
 f.test("Codswallop")