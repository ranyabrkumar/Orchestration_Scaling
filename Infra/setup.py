import boto3
import base64
import json
from botocore.exceptions import ClientError

# --------- CONFIG ---------
AWS_REGION = "us-west-2"
PROJECT_NAME = "mernapp-rbrk"
AMI_ID = "ami-05f991c49d264708f"
ECR_IMAGES = {
    "backend1": "975050024946.dkr.ecr.us-west-2.amazonaws.com/myapp-backend1:latest",
    "backend2": "975050024946.dkr.ecr.us-west-2.amazonaws.com/myapp-backend2:latest",
    "frontend": "975050024946.dkr.ecr.us-west-2.amazonaws.com/myapp-frontend:latest",
}
INSTANCE_TYPE = "t2.micro"
KEY_NAME = "Severless_rbrk"   # change to your EC2 key pair

ec2 = boto3.client("ec2", region_name=AWS_REGION)
iam = boto3.client("iam", region_name=AWS_REGION)
autoscaling = boto3.client("autoscaling", region_name=AWS_REGION)


# --------- VPC + SUBNETS ---------
def get_default_vpc():
    print("Fetching Default VPC...")
    vpcs = ec2.describe_vpcs(
        Filters=[{"Name": "isDefault", "Values": ["true"]}]
    )["Vpcs"]

    if not vpcs:
        raise Exception("No default VPC found in this region!")

    vpc_id = vpcs[0]["VpcId"]
    print(f"Using Default VPC: {vpc_id}")
    return vpc_id


def get_subnets(vpc_id):
    print("Fetching existing subnets from Default VPC...")
    subnets = ec2.describe_subnets(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    )["Subnets"]

    subnet_ids = [s["SubnetId"] for s in subnets]
    print(f"Using Subnets: {subnet_ids}")
    return subnet_ids


# --------- SECURITY GROUP ---------
def create_security_group(vpc_id):
    try:
        sg = ec2.create_security_group(
            GroupName=f"{PROJECT_NAME}-sg",
            Description="Security group for MERN app",
            VpcId=vpc_id,
        )
        sg_id = sg["GroupId"]

        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                 "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80,
                 "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                 {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443,
                 "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                {"IpProtocol": "tcp", "FromPort": 3000, "ToPort": 3000,
                 "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                {"IpProtocol": "tcp", "FromPort": 3001, "ToPort": 3001,
                 "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            ],
        )
        print(f"Created Security Group {sg_id}")
        return sg_id
    except ClientError as e:
        if "InvalidGroup.Duplicate" in str(e):
            print("Security group already exists, fetching existing one...")
            groups = ec2.describe_security_groups(
                Filters=[{"Name": "group-name", "Values": [f"{PROJECT_NAME}-sg"]}]
            )["SecurityGroups"]
            return groups[0]["GroupId"]
        else:
            raise


# --------- IAM ROLE ---------
def create_iam_role():
    role_name = f"{PROJECT_NAME}-role"
    instance_profile_name = f"{PROJECT_NAME}-instance-profile"

    try:
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }),
        )
        print(f"IAM Role {role_name} created.")
    except ClientError as e:
        if "EntityAlreadyExists" in str(e):
            print(f"IAM Role {role_name} already exists.")
        else:
            raise

    try:
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
        )
        print("Attached ECR read-only policy to role.")
    except Exception:
        pass

    try:
        iam.create_instance_profile(InstanceProfileName=instance_profile_name)
        iam.add_role_to_instance_profile(
            InstanceProfileName=instance_profile_name, RoleName=role_name
        )
        print(f"Instance profile {instance_profile_name} created.")
    except ClientError as e:
        if "EntityAlreadyExists" in str(e):
            print(f"Instance profile {instance_profile_name} already exists.")
        else:
            raise

    return instance_profile_name


# --------- LAUNCH TEMPLATE ---------
def create_launch_template(service_name, sg_id, instance_profile_name):
    user_data_script = f"""#!/bin/bash
    yum update -y
    yum install -y docker
    service docker start
    usermod -a -G docker ec2-user
    aws ecr get-login-password --region {AWS_REGION} | docker login --username AWS --password-stdin {ECR_IMAGES[service_name].split('/')[0]}
    docker run -d -p 3000:3000 {ECR_IMAGES[service_name]}
    """

    encoded_ud = base64.b64encode(user_data_script.encode("utf-8")).decode("utf-8")

    lt_name = f"{PROJECT_NAME}-{service_name}-lt"
    try:
        lt = ec2.create_launch_template(
            LaunchTemplateName=lt_name,
            LaunchTemplateData={
                "ImageId": "ami-05f991c49d264708f",  
                "InstanceType": INSTANCE_TYPE,
                "KeyName": KEY_NAME,
                "IamInstanceProfile": {"Name": instance_profile_name},
                "SecurityGroupIds": [sg_id],
                "UserData": encoded_ud,
            },
        )
        print(f"Launch Template {lt_name} created.")
        return lt["LaunchTemplate"]["LaunchTemplateId"]
    except ClientError as e:
        if "InvalidLaunchTemplateName.AlreadyExistsException" in str(e):
            print(f"Launch Template {lt_name} already exists, fetching existing...")
            lts = ec2.describe_launch_templates(
                LaunchTemplateNames=[lt_name]
            )["LaunchTemplates"]
            return lts[0]["LaunchTemplateId"]
        else:
            raise


# --------- AUTO SCALING GROUP ---------
def create_asg(service_name, lt_id, subnet_ids):
    asg_name = f"{PROJECT_NAME}-{service_name}-asg"
    try:
        autoscaling.create_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            LaunchTemplate={"LaunchTemplateId": lt_id, "Version": "$Latest"},
            MinSize=1,
            MaxSize=2,
            DesiredCapacity=1,
            VPCZoneIdentifier=",".join(subnet_ids),
            Tags=[{
                "Key": "Name", "Value": f"{PROJECT_NAME}-{service_name}", "PropagateAtLaunch": True
            }],
        )
        print(f"ASG {asg_name} created.")
    except ClientError as e:
        if "AlreadyExists" in str(e):
            print(f"ASG {asg_name} already exists, skipping.")
        else:
            raise


# --------- MAIN ---------
if __name__ == "__main__":
    vpc_id = get_default_vpc()
    subnet_ids = get_subnets(vpc_id)
    sg_id = create_security_group(vpc_id)
    instance_profile_name = create_iam_role()

    for service in ECR_IMAGES.keys():
        lt_id = create_launch_template(service, sg_id, instance_profile_name)
        create_asg(service, lt_id, subnet_ids)

    print("Infrastructure setup complete for all services in default VPC")
