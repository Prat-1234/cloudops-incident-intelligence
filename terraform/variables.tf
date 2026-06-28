variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Short name used as a prefix on every resource"
  type        = string
  default     = "cloudops"
}

variable "alert_email" {
  description = "Email address that receives SNS incident alerts"
  type        = string
}

variable "github_org" {
  description = "Your GitHub username"
  type        = string
  default     = "Prat-1234"
}

variable "github_repo" {
  description = "GitHub repo name"
  type        = string
  default     = "cloudops-incident-intelligence"
}