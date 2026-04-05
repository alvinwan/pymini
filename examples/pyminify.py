def a(event,context):
 e='RequestType';f='PhysicalResourceId';g='None';h='Status';i='SUCCESS';j='Tags';k='OldResourceProperties';l.info(event);a,m,n,o,p,q,r,s,t=(event,create_cert,add_tags,validate,wait_for_issuance,context,send,reinvoke,acm)
 try:
  b=hashlib.new('md5',(a['RequestId']+a['StackId']).encode()).hexdigest();c=a['ResourceProperties']
  if a[e]=='Create':
   a[f]=g;a[f]=m(c,b);n(a[f],c);o(a[f],c)
   if p(a[f],q):a[h]=i;return r(a)
   else:return s(a,q)
  elif a[e]=='Delete':
   if a[f]!=g:t.delete_certificate(CertificateArn=a[f])
   a[h]=i;return r(a)
  elif a[e]=='Update':
   if replace_cert(a):
    a[f]=m(c,b);n(a[f],c);o(a[f],c)
    if not p(a[f],q):return s(a,q)
   else:
    if j in a[k]:t.remove_tags_from_certificate(CertificateArn=a[f],Tags=a[k][j])
    n(a[f],c)
   a[h]=i;return r(a)
  else:raise RuntimeError('Unknown RequestType')
 except Exception as d:l.exception('');a[h]='FAILED';a['Reason']=str(d);return r(a)
 del (a,m,n,o,p,q,r,s,t)
handler=a