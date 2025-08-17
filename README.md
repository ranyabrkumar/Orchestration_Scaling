# Sample MERN with Microservices - AWS Deployment

This project demonstrates the deployment of a MERN (MongoDB, Express.js, React.js, Node.js) application using AWS services, containerization, CI/CD pipelines, and Infrastructure as Code. The application is structured as microservices and is fully deployable on EC2, EKS, and AWS Lambda.

---

## Project Repository

Original Repository: [SampleMERNwithMicroservices](https://github.com/UnpredictablePrashant/SampleMERNwithMicroservices)  
Forked Repository: [repo](https://github.com/ranyabrkumar/SampleMERNwithMicroservices.git)

For updating your fork with the main repository:  
[Pull new updates from original repository](https://stackoverflow.com/questions/3903817/pull-new-updates-from-original-github-repository-into-forked-github-repository)

---

## Project Steps

### Step 1: Set Up AWS Environment

1. **AWS CLI and Boto3**
   - Install AWS CLI and configure it with your AWS credentials.
     
     ```
     curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" 
      sudo apt-get install -y unzip 
      unzip awscliv2.zip 
      sudo ./aws/install 
     ```
     ```bash
          aws configure
     ```
     ![AWSCONFIGURE](https://github.com/user-attachments/assets/258e7718-392c-4498-b538-70bd65f2cd87)

# Provide AWS Access Key, Secret Key, region, and output format
   - Install Boto3 for Python and configure it.
  
     ```
     pip install boto3
     ```

---

### Step 2: Prepare the MERN Application

1. **Containerize the Application**
   - Create Dockerfiles for frontend and backend components.
   - Ensure both components are containerized.
![localtest-FEsrv](https://github.com/user-attachments/assets/956b69fd-c4a4-4227-a125-02dab65074e7)
![localtest-profilesrv](https://github.com/user-attachments/assets/cbf341f6-426d-4f66-81cc-4b3fd0872a61)
![localtest-hellosrv](https://github.com/user-attachments/assets/81f99e3e-8f70-4f06-91de-b6e0648f0b5d)

2. **Push Docker Images to Amazon ECR**

   - Login to AWS console, go to ECR and create a repository
   - Login to ECR repository
     ```
     aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin <account_id>.dkr.ecr.<region>.amazonaws.com
     ```
   - Build Docker images for frontend and backend.
     ```
     docker build -t <reponame> .
     docker tag <reponame>:<tagname> <account_id>.dkr.ecr.<region>.amazonaws.com/<reponame>:<tagname>
     ```
   - Create ECR repositories for each image.
   - Push Docker images to the respective ECR repositories.
     ```
     docker push <account_id>.dkr.ecr.<region>.amazonaws.com/<reponame>:<tagname>
     ```

     ![ECR_ImagesDetails_AfterJenkinsBuild_success](https://github.com/user-attachments/assets/0a9d2764-9700-4e58-99ff-70a22f0ab2b2)


---

### Step 3: Version Control

1. **Use AWS CodeCommit OR GitHub**
   - Create a CodeCommit\GitHub repository.
   - Push the MERN application source code to CodeCommit\GitHub.

---

### Step 4: Continuous Integration with Jenkins

1. **Set Up Jenkins**
   - Install Jenkins on an EC2 instance.
   - Configure required plugins.
     ```
     Docker,AWSCLI,Pipeline,Github Intergation
     ```

2. **Create Jenkins Jobs**
   - Jobs for building and pushing Docker images to ECR.
   - Trigger jobs automatically on new commits in CodeCommit/GitHub.

![jenkins_buildStages](https://github.com/user-attachments/assets/e5b8a333-2dcf-4476-8fb2-1f53727e2c82)

![GITHUB_HOOK_LOG](https://github.com/user-attachments/assets/4be7a71c-c288-4cdc-9170-c481114289a9)

---

### Step 5: Infrastructure as Code (IaC) with Boto3

1. **Define Infrastructure**
   - Use Boto3 Python scripts to define VPC[used default one], subnets, security groups.
   - Define an Auto Scaling Group (ASG) for backend.
   - Create AWS Lambda functions if needed.
 ---

### Step 6: Deploy Backend Services

1. **Deploy Backend on EC2 with ASG**
   - Deploy Dockerized backend application in the ASG.
     
![Iac_log](https://github.com/user-attachments/assets/e2acb8ac-68d9-4087-907d-229a25daeb62)

---

### Step 7: Set Up Networking

1. **Load Balancer**
   - Create an Elastic Load Balancer (ELB) for the backend ASG.
     1. Create ALB with Internet facing type, with VPC we have used, select 2 atleast 2 subnet, SG 

2. **DNS Configuration**
   - Set up DNS using Route 53 or any other DNS service like GODaddy.com
     1. Get a domain and add DNS entry in domain
     2. CNAME > www or @ > ALB ARN >TTL [custom 600sec]
        
   ![ALB_DNS](https://github.com/user-attachments/assets/5bff6070-ae32-4dd8-93e0-4f78f0d27719)

---

### Step 8: Deploy Frontend Services

1. **Deploy Frontend on EC2**
   - Deploy Dockerized frontend application on EC2 instances.

  ```
      python3 Infra/Infra_setup.py
   ```
---

### Step 9: AWS Lambda Deployment

1. **Create Lambda Functions**
   - Use Lambda for specific tasks within the application.
     1.  create a lambda function, with IAM Role [AWSLambdaBasicExecutionRole,AmazonS3FullAccess] 
     2. create a layer for mongodump [you can create.zip file attach directly or though s3]
   - Example: Backup MongoDB database to S3 with timestamp.
     
    ```
    python Infra/lambda_function.py
    ```
![CLoudWatch_Log_lamdafn_MongoBkp](https://github.com/user-attachments/assets/2c7f8cc2-9d44-49ed-92e6-8fcd968b3a3e)

    ![subscription_confirmation](https://github.com/user-attachments/assets/6812f61d-bfb1-4e27-8c39-f57139eb9a9d)

![S3_Aft_lambda_execution](https://github.com/user-attachments/assets/f934ce6a-931f-408e-8eb7-889d8eeb538f)


---


## Step 10: Kubernetes (EKS) Deployment

### 1. Create EKS Cluster

Use `eksctl` or AWS tools to create an EKS cluster:

```bash
eksctl create cluster \
  --name mern-app-deployment-rbrk4 \
  --region us-west-2 \
  --nodegroup-name standard-workers \
  --node-type t2.micro \
  --nodes 4 \
  --nodes-min 1 \
  --nodes-max 6
```

<img width="1684" height="841" alt="EKS Deployment" src="https://github.com/user-attachments/assets/212ca213-dd66-4219-9f58-f05ce2647313" />



2. **Deploy Application with Helm**
   - Package and deploy the MERN application using Helm.
    ``` helm create <chart-name>
    ```
  - Create or update Value.yaml and templates yaml files
  - Install helm chart
    ```
    helm install <releasename> ./<chart-directory>

    ```
  - To uninstall helm chart
  ```
  helm uninstall <releasename>  
```

- To package helm chart

   ```
      helm package ./<chart-directory>
   ```
![helm_frontend](https://github.com/user-attachments/assets/ca59ca84-73c5-4d13-8c60-20fcc533e80d)
![helm_helloservice](https://github.com/user-attachments/assets/85c8a9f7-9ee2-4824-906a-a8c3d624f813)
![helm_profileservice](https://github.com/user-attachments/assets/770f8e30-96d4-416d-a963-34c87f40ea57)

---
### Step 11: Monitoring and Logging

1. **Monitoring**
   - Use CloudWatch to monitor application health and set alarms.
![cloudwatch_Alarm_SetUp](https://github.com/user-attachments/assets/a64b1dce-6214-4271-82ef-d4aed437ebaa)

2. **Logging**
   - Use CloudWatch Logs or another logging solution for collecting logs.
![cloudwatch_log_monitoring](https://github.com/user-attachments/assets/018aeaeb-e742-43c5-bebf-a5d8e913ef96)

---

### Step 12: Documentation

1. **Document Architecture**
   - Document the deployment architecture and steps.
   - Maintain all documentation on GitHub.

---

### Step 13: Final Checks

1. **Validate Deployment**
   - Ensure the MERN application is accessible and functioning correctly.
<img width="925" height="170" alt="image" src="https://github.com/user-attachments/assets/dada50c4-e32a-468c-89b2-75592b119413" />

---

### Bonus: ChatOps Integration (Optional)

1. **Create SNS Topics**
   - Use Boto3 to create topics for deployment events (success/failure).
![snsTopic](https://github.com/user-attachments/assets/24036ddc-7a1c-4669-87a6-f4d82f1ce569)


2. **Create Lambda for ChatOps**
   - Write Lambda functions that send notifications to SNS topics.

3. **Integrate with Messaging Platform**
   - Connect SNS notifications to Slack, MS Teams, or Telegram.

4. **Configure SES**
   - For email notifications if required.

---

## Notes

- Make sure AWS credentials are properly configured.
- Ensure Docker images are correctly tagged and pushed to ECR.
- All infrastructure provisioning can be automated using Boto3 scripts.

