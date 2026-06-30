# CloudOps Incident Intelligence Platform

> **AI-powered serverless incident management on AWS** — built to demonstrate Cloud Support and DevOps engineering skills.

**🔗 Live Dashboard:** [View on S3](http://cloudops-dashboard-353625676485.s3-website-us-east-1.amazonaws.com)

---

## What This Project Demonstrates

| Skill Area | How It's Used |
|---|---|
| **AWS Lambda** | Ingestion pipeline, REST API handler, GuardDuty forwarder |
| **API Gateway** | REST API with Lambda proxy integration, CORS |
| **DynamoDB** | Incident storage with GSI for severity-based queries, TTL, PITR |
| **Amazon Bedrock** | AI root-cause analysis via Nova Micro model (with rule-based fallback) |
| **CloudWatch** | Log ingestion, Subscription Filters, custom log groups |
| **SNS** | CRITICAL incident alerts + GuardDuty finding notifications |
| **GuardDuty** | Threat detection with EventBridge routing |
| **S3** | Static website hosting for the live dashboard |
| **VPC** | Private subnet, NAT Gateway, Security Groups, VPC Endpoints |
| **IAM** | Least-privilege roles per Lambda, OIDC for GitHub Actions |
| **Terraform** | Full IaC — every resource provisioned declaratively |
| **Docker / ECR** | Lambda functions packaged as container images |
| **GitHub Actions** | CI/CD — test → build → push → deploy |

---

## Architecture
EC2 (private subnet)          EventBridge (5-min schedule)
│ CloudWatch logs                  │ synthetic events
│ Subscription Filter              │
└──────────────────┬───────────────┘
▼
Lambda: ingestion
│        │
Bedrock AI    DynamoDB
root cause    incidents
(with rule-     │
based          │
fallback)      │
│        │
SNS      API Gateway
(CRITICAL    │
alerts)     ▼
Lambda: api
│
DynamoDB read/write
│
S3 Dashboard ← public URL (resume link)
GuardDuty Findings → EventBridge → Lambda: guardduty-forwarder → SNS
---

## Project Structure
cloudops-incident-intelligence/
├── terraform/
│   ├── main.tf           # Provider, backend
│   ├── variables.tf      # Input variables
│   ├── vpc.tf             # VPC, subnets, NAT, security groups, endpoints
│   ├── iam.tf             # Lambda roles, EC2 profile, GitHub OIDC
│   ├── dynamodb.tf        # Incidents table + GSI
│   ├── s3.tf               # Dashboard bucket (public), reports bucket (private)
│   ├── sns.tf              # Alerts topic + email subscription
│   ├── lambda.tf           # ECR, Lambda functions, CW subscription filter
│   ├── api_gateway.tf      # REST API, routes, CORS, deployment
│   ├── guardduty.tf        # GuardDuty detector, EventBridge rules
│   ├── ec2.tf               # Log generator instance (kept for reference)
│   └── outputs.tf           # Dashboard URL, API URL, role ARNs
├── lambdas/
│   ├── ingestion/handler.py    # CW log → Bedrock (with fallback) → DynamoDB → SNS
│   ├── api/handler.py          # REST CRUD for incidents
│   └── guardduty/handler.py    # GuardDuty finding → SNS
├── dashboard/
│   └── index.html              # S3-hosted live dashboard
├── .github/workflows/
│   └── deploy.yml              # CI/CD pipeline
├── Dockerfile                  # Multi-target Lambda container image
├── requirements.txt
└── README.md
---

## Deployment Guide

### Prerequisites
- AWS CLI configured (`aws configure`)
- Terraform >= 1.6
- Docker Desktop running

### Step 1 — Terraform init & apply

```powershell
cd terraform
$env:TF_VAR_alert_email="your@email.com"
terraform init
terraform plan
terraform apply
```

### Step 2 — Build and push Docker images

```powershell
$token = aws ecr get-login-password --region us-east-1
docker login --username AWS --password $token <ecr_repository_url>

cd ..
docker build --platform linux/amd64 --target ingestion -t <ecr_repository_url>:ingestion-latest --provenance=false .
docker build --platform linux/amd64 --target api -t <ecr_repository_url>:api-latest --provenance=false .
docker build --platform linux/amd64 --target guardduty -t <ecr_repository_url>:guardduty-latest --provenance=false .

docker push <ecr_repository_url>:ingestion-latest
docker push <ecr_repository_url>:api-latest
docker push <ecr_repository_url>:guardduty-latest
```

### Step 3 — Re-run Terraform to create Lambda functions

```powershell
cd terraform
terraform apply
```

### Step 4 — Wire up the dashboard

Edit `dashboard/index.html`, set `API_BASE` to your `api_base_url` output, then:

```powershell
cd ..
aws s3 sync dashboard/ s3://<dashboard_bucket_name>/ --delete
```

### Step 5 — Enable Bedrock model access (optional, requires billing)

AWS Console → Bedrock → Model access → Amazon Nova Micro → Request access.

Until then, the ingestion Lambda automatically uses rule-based fallback analysis — no errors, no broken pipeline.

### Step 6 — Set up GitHub Actions CI/CD

Add `AWS_ROLE_ARN` to repo secrets (Settings → Secrets and variables → Actions):
terraform output github_actions_role_arn

Every push to `main` will now build, push, and deploy automatically.

---

## Testing the Live API

```powershell
# List all incidents
Invoke-WebRequest -Uri "<api_base_url>/incidents" -UseBasicParsing

# Create a simulated incident
Invoke-WebRequest -Method POST -Uri "<api_base_url>/incidents/simulate" -UseBasicParsing

# Filter by severity
Invoke-WebRequest -Uri "<api_base_url>/incidents?severity=CRITICAL" -UseBasicParsing

# Resolve an incident
Invoke-WebRequest -Method DELETE -Uri "<api_base_url>/incidents/<incident-id>" -UseBasicParsing
```

---

## Cost Estimate (always-on deployment)

| Service | Monthly Cost |
|---|---|
| Lambda | ~$0.00 (free tier) |
| API Gateway | ~$0.004 |
| DynamoDB | ~$0.25 |
| S3 | ~$0.00 |
| CloudWatch Logs | ~$0.50 |
| GuardDuty | Free for 30 days, then ~$1-4 |
| NAT Gateway | ~$32 |
| **Total** | **~$33/month, or under $5/month with NAT Gateway destroyed** |

> To minimize cost, destroy the NAT Gateway when not actively demonstrating the EC2 flow:
> `terraform destroy -target aws_nat_gateway.nat -target aws_eip.nat`

---

## Interview Talking Points

**"Walk me through the architecture"**
> Log events from EC2 (or a scheduled simulator) flow into the ingestion Lambda. It calls Amazon Bedrock for AI root-cause analysis — with a rule-based fallback if Bedrock access isn't configured — stores the incident in DynamoDB, and alerts via SNS for CRITICAL severity. API Gateway exposes a REST API consumed by the S3-hosted dashboard. GuardDuty monitors for security threats, routed via EventBridge to a dedicated forwarder Lambda.

**"How does CI/CD work?"**
> GitHub Actions uses OIDC — no long-lived AWS credentials stored as secrets. On every push to main, it builds three Docker image targets from one Dockerfile, pushes to ECR, updates each Lambda's code, and syncs the dashboard to S3.

**"Why Lambda over EC2 for the always-on deployment?"**
> EC2 incurs cost 24/7. An EventBridge-scheduled Lambda achieves the same demo effect at near-zero cost, while the EC2 Terraform code stays in the repo to demonstrate that skill set without paying for idle compute.
