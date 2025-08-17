import boto3
import base64
import time

AWS_REGION = "us-west-2"
PROJECT_NAME = "mernapp-rbrk-v1"
AMI_ID = "ami-05f991c49d264708f"  # Ubuntu 20.04 LTS

ECR_IMAGES = {
    "backend1": "975050024946.dkr.ecr.us-west-2.amazonaws.com/ranyabrkumar:mern-helloservice_v20",
    "backend2": "975050024946.dkr.ecr.us-west-2.amazonaws.com/ranyabrkumar:mern-profileservice_v20",
    "frontend": "975050024946.dkr.ecr.us-west-2.amazonaws.com/ranyabrkumar:mern-frontend_v20",
    "mongodb": "mongo:latest",
}

INSTANCE_TYPE = "t2.micro"
KEY_NAME = "Severless_rbrk"

ec2 = boto3.client("ec2", region_name=AWS_REGION)
autoscaling = boto3.client("autoscaling", region_name=AWS_REGION)
elbv2 = boto3.client("elbv2", region_name=AWS_REGION)
iam = boto3.client("iam", region_name=AWS_REGION)

# ----------------- VPC & Subnets -----------------
def get_default_vpc():
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    return vpcs["Vpcs"][0]["VpcId"]

def get_default_subnets(vpc_id):
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    return [s["SubnetId"] for s in subnets["Subnets"]]

def create_security_groups(vpc_id):
    sgs = {}
    for name, desc in [("fe", "Frontend SG"), ("be", "Backend SG"), ("mongo", "MongoDB SG")]:
        # Check if SG exists
        existing_sgs = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [f"{PROJECT_NAME}-{name}-sg"]}]
        )["SecurityGroups"]
        
        if existing_sgs:
            sgs[name] = existing_sgs[0]["GroupId"]
        else:
            sg = ec2.create_security_group(GroupName=f"{PROJECT_NAME}-{name}-sg", Description=desc, VpcId=vpc_id)
            sgs[name] = sg["GroupId"]

    # Ingress rules
    rules = {
        "fe": [
            {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        ],
        "be": [
            {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "UserIdGroupPairs":[{"GroupId": sgs["fe"]}]},
            {"IpProtocol": "tcp", "FromPort": 3001, "ToPort": 3002, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        ],
        "mongo": [
            {"IpProtocol": "tcp", "FromPort": 27017, "ToPort": 27017, "UserIdGroupPairs":[{"GroupId": sgs["be"]}]},
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        ]
    }

    # Apply ingress rules if not already present
    for name, perms in rules.items():
        existing_perms = ec2.describe_security_groups(GroupIds=[sgs[name]])["SecurityGroups"][0]["IpPermissions"]
        # Only add rules that don't exist
        for perm in perms:
            if perm not in existing_perms:
                try:
                    ec2.authorize_security_group_ingress(GroupId=sgs[name], IpPermissions=[perm])
                except ec2.exceptions.ClientError as e:
                    if "InvalidPermission.Duplicate" in str(e):
                        pass  # Already exists

    print(f"Created/Found security groups: {sgs}")
    return sgs["fe"], sgs["be"], sgs["mongo"]

# ----------------- IAM Role & Instance Profile -----------------
def create_instance_profile():
    role_name = f"{PROJECT_NAME}-ec2-role"
    profile_name = f"{PROJECT_NAME}-ec2-profile"

    # Create Role
    try:
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument="""{
                "Version":"2012-10-17",
                "Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]
            }"""
        )
        iam.attach_role_policy(RoleName=role_name, PolicyArn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly")
        iam.attach_role_policy(RoleName=role_name, PolicyArn="arn:aws:iam::aws:policy/AmazonS3FullAccess")
    except iam.exceptions.EntityAlreadyExistsException:
        pass

    # Create Instance Profile
    try:
        iam.create_instance_profile(InstanceProfileName=profile_name)
    except iam.exceptions.EntityAlreadyExistsException:
        pass

    # Attach Role to Instance Profile
    attached = False
    for _ in range(10):
        try:
            iam.add_role_to_instance_profile(InstanceProfileName=profile_name, RoleName=role_name)
            attached = True
            break
        except iam.exceptions.LimitExceededException:
            attached = True
            break
        except Exception:
            time.sleep(2)  # wait for eventual consistency

    if not attached:
        raise Exception("Failed to attach role to instance profile")

    #  Wait until AWS fully propagates it
    while True:
        try:
            resp = iam.get_instance_profile(InstanceProfileName=profile_name)
            break
        except iam.exceptions.NoSuchEntityException:
            time.sleep(2)

    return profile_name

# ----------------- User Data -----------------
def build_user_data(service):
    port_map = {"frontend": ("3000", "80"), "backend1": ("3001", "3001"), "backend2": ("3002", "3002"), "mongodb": ("27017","27017")}
    container_port, host_port = port_map[service]
    image = ECR_IMAGES[service]

    mongo_uri = ""
    if service in ["backend1","backend2"]:
        mongo_ip = "$(aws ec2 describe-instances --filters 'Name=tag:Name,Values='mernapp-rbrk-v1-mongo' --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
        mongo_uri = f"-e MONGO_URI=\"mongodb://{mongo_ip}:27017/mernapp\""

    return f"""#!/bin/bash
apt-get update -y
apt-get upgrade -y
apt-get install -y apt-transport-https ca-certificates curl software-properties-common unzip
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu focal stable"
apt-get update -y
apt-get install -y docker-ce
systemctl start docker
systemctl enable docker
usermod -aG docker ubuntu

curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" 
sudo apt-get install -y unzip 
unzip awscliv2.zip 
sudo ./aws/install 
rm -rf awscliv2.zip aws
REGION={AWS_REGION} 
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
sudo docker run -d --name {PROJECT_NAME}-{service} -p {host_port}:{container_port} {image} {mongo_uri}
"""

# ----------------- Launch Template -----------------
def create_launch_template(name, sg_id, instance_profile):
    try:
        service = name.split("-")[3]
    except:
        service = "mongodb"

    if service=="fe": service="frontend"
    elif service=="be1": service="backend1"
    elif service=="be2": service="backend2"
    else: service="mongodb"

    userdata = base64.b64encode(build_user_data(service).encode("utf-8")).decode("utf-8")

    # Check if LT exists
    try:
        existing = ec2.describe_launch_templates(LaunchTemplateNames=[name])
        return existing["LaunchTemplates"][0]["LaunchTemplateId"]
    except:
        pass

    resp = ec2.create_launch_template(
        LaunchTemplateName=name,
        LaunchTemplateData={"ImageId":AMI_ID,"InstanceType":INSTANCE_TYPE,"KeyName":KEY_NAME,"IamInstanceProfile":{"Name":instance_profile},"SecurityGroupIds":[sg_id],"UserData":userdata}
    )
    time.sleep(2)  # Wait for LT to be created
    print(f"Created Launch Template: {name}")
    return resp["LaunchTemplate"]["LaunchTemplateId"]

# ----------------- Auto Scaling Group -----------------
def create_asg(name, lt_id, subnets, tg_arns=[]):
    # try:
    #     autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[name])
    #     print(f"Auto Scaling Group {name} already exists.")
    #     return
    # except:
    #     pass

    autoscaling.create_auto_scaling_group(
        AutoScalingGroupName=name,
        LaunchTemplate={"LaunchTemplateId": lt_id, "Version":"$Latest"},
        MinSize=1, MaxSize=2, DesiredCapacity=1,
        VPCZoneIdentifier=",".join(subnets),
        TargetGroupARNs=tg_arns
    )
    print(f"Created Auto Scaling Group: {name}")

# ----------------- ALB & Target Groups -----------------
def create_target_group(name, port, vpc_id):
    try:
        existing = elbv2.describe_target_groups(Names=[name])
        return existing["TargetGroups"][0]["TargetGroupArn"]
    except:
        pass
    resp = elbv2.create_target_group(Name=name, Protocol="HTTP", Port=port, VpcId=vpc_id, TargetType="instance", HealthCheckProtocol="HTTP", HealthCheckPort=str(port), HealthCheckPath="/")
    time.sleep(2)  # Wait for TG to be created
    print(f"Created Target Group: {name}")
    return resp["TargetGroups"][0]["TargetGroupArn"]

def create_alb(name, subnets, sg_id):
    try:
        existing = elbv2.describe_load_balancers(Names=[name])

        return existing["LoadBalancers"][0]["LoadBalancerArn"]
    except:
        pass
    resp = elbv2.create_load_balancer(Name=name, Subnets=subnets, SecurityGroups=[sg_id], Scheme="internet-facing", Type="application", IpAddressType="ipv4")
    time.sleep(2)  # Wait for ALB to be created
    print(f"Created Application Load Balancer: {name}")
    return resp["LoadBalancers"][0]["LoadBalancerArn"]

def create_listener(alb_arn, tg_arn, port):
    listeners = elbv2.describe_listeners(LoadBalancerArn=alb_arn).get("Listeners",[])
    for l in listeners:
        if l["Port"]==port: return l["ListenerArn"]
    resp = elbv2.create_listener(LoadBalancerArn=alb_arn, Protocol="HTTP", Port=port, DefaultActions=[{"Type":"forward","TargetGroupArn":tg_arn}])
    time.sleep(2)  # Wait for Listener to be created
    print(f"Created Listener on port {port} for ALB: {alb_arn}")
    return resp["Listeners"][0]["ListenerArn"]

# ----------------- Main -----------------
if __name__=="__main__":
    vpc_id = get_default_vpc()
    subnets = get_default_subnets(vpc_id)
    sg_fe, sg_be, sg_mongo = create_security_groups(vpc_id)
    instance_profile = create_instance_profile()

    # MongoDB EC2
    ec2.run_instances(
        ImageId=AMI_ID, InstanceType=INSTANCE_TYPE, KeyName=KEY_NAME,
        IamInstanceProfile={"Name": instance_profile}, SecurityGroupIds=[sg_mongo],
        MinCount=1, MaxCount=1,
        UserData=base64.b64encode(build_user_data("mongodb").encode("utf-8")).decode("utf-8"),
        SubnetId=subnets[0],
        TagSpecifications=[{"ResourceType":"instance","Tags":[{"Key":"Name","Value":f"{PROJECT_NAME}-mongo"}]}]
    )

    # ALB & Target Groups
    alb_arn = create_alb(f"{PROJECT_NAME}-alb", subnets, sg_fe)
    tg_fe = create_target_group(f"{PROJECT_NAME}-fe-tg", 80, vpc_id)
    tg_be1 = create_target_group(f"{PROJECT_NAME}-be1-tg", 3001, vpc_id)
    tg_be2 = create_target_group(f"{PROJECT_NAME}-be2-tg", 3002, vpc_id)
    create_listener(alb_arn, tg_fe, 80)
    create_listener(alb_arn, tg_be1, 3001)
    create_listener(alb_arn, tg_be2, 3002)

    # Backend1
    lt_be1 = create_launch_template(f"{PROJECT_NAME}-be1-lt", sg_be, instance_profile)
    create_asg(f"{PROJECT_NAME}-be1-asg", lt_be1, subnets, [tg_be1])

    # Backend2
    lt_be2 = create_launch_template(f"{PROJECT_NAME}-be2-lt", sg_be, instance_profile)
    create_asg(f"{PROJECT_NAME}-be2-asg", lt_be2, subnets, [tg_be2])

    # Frontend
    lt_fe = create_launch_template(f"{PROJECT_NAME}-fe-lt", sg_fe, instance_profile)
    create_asg(f"{PROJECT_NAME}-fe-asg", lt_fe, subnets, [tg_fe])

    print("Infrastructure setup complete with ALB, Target Groups, ASGs, and MongoDB.")
    print(f"ALB ARN: {alb_arn}")