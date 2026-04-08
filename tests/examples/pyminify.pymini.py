def a(event,context):
 c='RequestType';d='PhysicalResourceId';e='None';f='Status';g='SUCCESS';h='Tags';i='OldResourceProperties';l.info(event);j,k,m,n,o,p,q,r,s=(event,create_cert,add_tags,validate,wait_for_issuance,context,send,reinvoke,acm)
 try:
  a=hashlib.new('md5',(j['RequestId']+j['StackId']).encode()).hexdigest();b=j['ResourceProperties']
  if j[c]=='Create':
   j[d]=e;j[d]=k(b,a);m(j[d],b);n(j[d],b)
   if o(j[d],p):j[f]=g;return q(j)
   else:return r(j,p)
  elif j[c]=='Delete':
   if j[d]!=e:s.delete_certificate(CertificateArn=j[d])
   j[f]=g;return q(j)
  elif j[c]=='Update':
   if replace_cert(j):
    j[d]=k(b,a);m(j[d],b);n(j[d],b)
    if not o(j[d],p):return r(j,p)
   else:
    if h in j[i]:s.remove_tags_from_certificate(CertificateArn=j[d],Tags=j[i][h])
    m(j[d],b)
   j[f]=g;return q(j)
  else:raise RuntimeError('Unknown RequestType')
 except Exception as b:l.exception('');j[f]='FAILED';j['Reason']=str(b);return q(j)
 del (j,k,m,n,o,p,q,r,s)
handler=a
