def a(event,context):
 f='RequestType';g='PhysicalResourceId';h='None';i='Status';j='SUCCESS';k='Tags';m='OldResourceProperties';l.info(event);n,o,p,q,r,s,t,u,v=(event,create_cert,add_tags,validate,wait_for_issuance,context,send,reinvoke,acm)
 try:
  b=hashlib.new('md5',(n['RequestId']+n['StackId']).encode()).hexdigest();c=n['ResourceProperties']
  if n[f]=='Create':
   n[g]=h;n[g]=o(c,b);p(n[g],c);q(n[g],c)
   if r(n[g],s):n[i]=j;return t(n)
   else:return u(n,s)
  elif n[f]=='Delete':
   if n[g]!=h:v.delete_certificate(CertificateArn=n[g])
   n[i]=j;return t(n)
  elif n[f]=='Update':
   if replace_cert(n):
    n[g]=o(c,b);p(n[g],c);q(n[g],c)
    if not r(n[g],s):return u(n,s)
   else:
    if k in n[m]:v.remove_tags_from_certificate(CertificateArn=n[g],Tags=n[m][k])
    p(n[g],c)
   n[i]=j;return t(n)
  else:raise RuntimeError('Unknown RequestType')
 except Exception as d:l.exception('');n[i]='FAILED';n['Reason']=str(d);return t(n)
 del (n,o,p,q,r,s,t,u,v)
handler=a