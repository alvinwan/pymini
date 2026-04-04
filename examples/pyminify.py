def a(event,context):
 l.info(event)
 try:
  b=hashlib.new('md5',(event['RequestId']+event['StackId']).encode()).hexdigest();c=event['ResourceProperties']
  if event['RequestType']=='Create':
   event['PhysicalResourceId']='None';event['PhysicalResourceId']=create_cert(c,b);add_tags(event['PhysicalResourceId'],c);validate(event['PhysicalResourceId'],c)
   if wait_for_issuance(event['PhysicalResourceId'],context):event['Status']='SUCCESS';return send(event)
   else:return reinvoke(event,context)
  elif event['RequestType']=='Delete':
   if event['PhysicalResourceId']!='None':acm.delete_certificate(CertificateArn=event['PhysicalResourceId'])
   event['Status']='SUCCESS';return send(event)
  elif event['RequestType']=='Update':
   if replace_cert(event):
    event['PhysicalResourceId']=create_cert(c,b);add_tags(event['PhysicalResourceId'],c);validate(event['PhysicalResourceId'],c)
    if not wait_for_issuance(event['PhysicalResourceId'],context):return reinvoke(event,context)
   else:
    if 'Tags' in event['OldResourceProperties']:acm.remove_tags_from_certificate(CertificateArn=event['PhysicalResourceId'],Tags=event['OldResourceProperties']['Tags'])
    add_tags(event['PhysicalResourceId'],c)
   event['Status']='SUCCESS';return send(event)
  else:raise RuntimeError('Unknown RequestType')
 except Exception as d:l.exception('');event['Status']='FAILED';event['Reason']=str(d);return send(event)
handler=a