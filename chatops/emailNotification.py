import boto3

ses = boto3.client('ses')

def send_email(subject, body, to_addresses):
    ses.send_email(
        Source='ranyabrkumar@gamil.com',
        Destination={'ToAddresses': to_addresses},
        Message={
            'Subject': {'Data': subject},
            'Body': {'Text': {'Data': body}}
        }
    )
