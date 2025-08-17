import boto3

sns = boto3.client('sns')

def create_sns_topic(topic_name):
    response = sns.create_topic(Name=topic_name)
    return response['TopicArn']

success_topic_arn = create_sns_topic("DeploymentSuccess")
failure_topic_arn = create_sns_topic("DeploymentFailure")

print("Success ARN:", success_topic_arn)
print("Failure ARN:", failure_topic_arn)
