import boto3
import json
import time
import zipfile
import os

# ----------------- Configuration -----------------
AWS_REGION = "us-west-2"
LAMBDA_NAME = "MongoDBBackupLambda"
LAMBDA_ROLE_NAME = "MongoDBBackupLambdaRole"
S3_BUCKET = "mernapp-db-rbrk2"
MONGO_URI = "mongodb://44.250.98.224:27017/mernapp"
RETENTION_DAYS = "7"
LAMBDA_FILE = "Infra\lambda_function.py"   # Your Lambda code
LAMBDA_ZIP = "lambda_function.zip"
LAYER_ARN = "arn:aws:lambda:us-west-2:975050024946:layer:mongodump_rbrk:1"  # Existing layer ARN

# ----------------- AWS Clients -----------------
iam = boto3.client("iam")
lambda_client = boto3.client("lambda", region_name=AWS_REGION)

# ----------------- 1. IAM Role -----------------
assume_role_policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
}

try:
    role = iam.create_role(
        RoleName=LAMBDA_ROLE_NAME,
        AssumeRolePolicyDocument=json.dumps(assume_role_policy)
    )
    print(f"Created IAM role: {LAMBDA_ROLE_NAME}")
except iam.exceptions.EntityAlreadyExistsException:
    role = iam.get_role(RoleName=LAMBDA_ROLE_NAME)
    print(f"IAM role already exists: {LAMBDA_ROLE_NAME}")

# Attach policies
iam.attach_role_policy(
    RoleName=LAMBDA_ROLE_NAME,
    PolicyArn="arn:aws:iam::aws:policy/AmazonS3FullAccess"
)
iam.attach_role_policy(
    RoleName=LAMBDA_ROLE_NAME,
    PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
)

role_arn = role["Role"]["Arn"]
print(f"IAM Role ARN: {role_arn}")

# Wait for IAM propagation
time.sleep(10)

# ----------------- 2. Package Lambda Function -----------------
if not os.path.exists(LAMBDA_FILE):
    raise FileNotFoundError(f"{LAMBDA_FILE} not found in the current directory.")

with zipfile.ZipFile(LAMBDA_ZIP, 'w', zipfile.ZIP_DEFLATED) as zipf:
    zipf.write(LAMBDA_FILE, arcname=os.path.basename(LAMBDA_FILE))

with open(LAMBDA_ZIP, "rb") as f:
    lambda_code = f.read()

print(f"Lambda ZIP created successfully: {LAMBDA_ZIP}")

# ----------------- 3. Create or Update Lambda Function -----------------
try:
    response = lambda_client.create_function(
        FunctionName=LAMBDA_NAME,
        Runtime="python3.11",
        Role=role_arn,
        Handler="lambda_function.lambda_handler",
        Code={"ZipFile": lambda_code},
        Timeout=300,
        MemorySize=512,
        Environment={
            "Variables": {
                "BUCKET_NAME": S3_BUCKET,
                "MONGO_URI": MONGO_URI,
                "RETENTION_DAYS": RETENTION_DAYS
            }
        },
        Layers=[LAYER_ARN]
    )
    print(f"Lambda function {LAMBDA_NAME} created successfully!")
except lambda_client.exceptions.ResourceConflictException:
    # Function exists → update code and configuration
    response = lambda_client.update_function_code(
        FunctionName=LAMBDA_NAME,
        ZipFile=lambda_code
    )
    lambda_client.update_function_configuration(
        FunctionName=LAMBDA_NAME,
        Environment={
            "Variables": {
                "BUCKET_NAME": S3_BUCKET,
                "MONGO_URI": MONGO_URI,
                "RETENTION_DAYS": RETENTION_DAYS
            }
        },
        Layers=[LAYER_ARN]
    )
    print(f"Lambda function {LAMBDA_NAME} updated successfully!")
