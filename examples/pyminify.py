def a(event,context):
 f='RequestType';g='PhysicalResourceId';h='None';i='Status';j='SUCCESS';k='Tags';m='OldResourceProperties';l.info(event)
 try:
  b=hashlib.new('md5',(event['RequestId']+event['StackId']).encode()).hexdigest();c=event['ResourceProperties']
  if event[f]=='Create':
   event[g]=h;event[g]=create_cert(c,b);add_tags(event[g],c);validate(event[g],c)
   if wait_for_issuance(event[g],context):event[i]=j;return send(event)
   else:return reinvoke(event,context)
  elif event[f]=='Delete':
   if event[g]!=h:acm.delete_certificate(CertificateArn=event[g])
   event[i]=j;return send(event)
  elif event[f]=='Update':
   if replace_cert(event):
    event[g]=create_cert(c,b);add_tags(event[g],c);validate(event[g],c)
    if not wait_for_issuance(event[g],context):return reinvoke(event,context)
   else:
    if k in event[m]:acm.remove_tags_from_certificate(CertificateArn=event[g],Tags=event[m][k])
    add_tags(event[g],c)
   event[i]=j;return send(event)
  else:raise RuntimeError('Unknown RequestType')
 except Exception as d:l.exception('');event[i]='FAILED';event['Reason']=str(d);return send(event)
handler=a