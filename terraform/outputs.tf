output "dashboard_url" {
  description = "Public S3 website URL — put this on your resume"
  value       = "http://${aws_s3_bucket.dashboard.bucket}.s3-website-${var.aws_region}.amazonaws.com"
}

output "api_base_url" {
  description = "API Gateway base URL — paste into dashboard/index.html"
  value       = aws_api_gateway_stage.prod.invoke_url
}

output "api_incidents_endpoint" {
  description = "Full endpoint for listing incidents"
  value       = "${aws_api_gateway_stage.prod.invoke_url}/incidents"
}

output "dynamodb_table_name" {
  description = "DynamoDB table name"
  value       = aws_dynamodb_table.incidents.name
}

output "ecr_repository_url" {
  description = "ECR repo URL — used in docker push and CI/CD"
  value       = aws_ecr_repository.lambdas.repository_url
}

output "sns_topic_arn" {
  description = "SNS alerts topic ARN"
  value       = aws_sns_topic.alerts.arn
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC — add to repo secrets as AWS_ROLE_ARN"
  value       = aws_iam_role.github_actions.arn
}

output "guardduty_detector_id" {
  description = "GuardDuty detector ID"
  value       = aws_guardduty_detector.main.id
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "private_subnet_id" {
  description = "Private subnet ID"
  value       = aws_subnet.private.id
}