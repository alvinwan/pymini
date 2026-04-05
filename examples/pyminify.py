def a(event,context):
 e='RequestType';f='PhysicalResourceId';g='None';h='Status';i='SUCCESS';j='Tags';k='OldResourceProperties';l.info(event);m,n,o,p,q,r,s,t,u=(event,create_cert,add_tags,validate,wait_for_issuance,context,send,reinvoke,acm)
 try:
  b=hashlib.new('md5',(m['RequestId']+m['StackId']).encode()).hexdigest();c=m['ResourceProperties']
  if m[e]=='Create':
   m[f]=g;m[f]=n(c,b);o(m[f],c);p(m[f],c)
   if q(m[f],r):m[h]=i;return s(m)
   else:return t(m,r)
  elif m[e]=='Delete':
   if m[f]!=g:u.delete_certificate(CertificateArn=m[f])
   m[h]=i;return s(m)
  elif m[e]=='Update':
   if replace_cert(m):
    m[f]=n(c,b);o(m[f],c);p(m[f],c)
    if not q(m[f],r):return t(m,r)
   else:
    if j in m[k]:u.remove_tags_from_certificate(CertificateArn=m[f],Tags=m[k][j])
    o(m[f],c)
   m[h]=i;return s(m)
  else:raise RuntimeError('Unknown RequestType')
 except Exception as d:l.exception('');m[h]='FAILED';m['Reason']=str(d);return s(m)
 del (m,n,o,p,q,r,s,t,u)
handler=a