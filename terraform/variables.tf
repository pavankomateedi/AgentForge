variable "aws_region" {
  description = "AWS region. Must be one with the full HIPAA-eligible service set (us-east-1, us-east-2, us-west-2, etc.)."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name — used in resource naming and tagging."
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["prod", "staging"], var.environment)
    error_message = "environment must be 'prod' or 'staging'."
  }
}

variable "owner_email" {
  description = "Email of the engineer / team owning these resources."
  type        = string
  default     = "PLACEHOLDER@example.com"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC. Must not overlap any peered network."
  type        = string
  default     = "10.42.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across. 2 is the HIPAA minimum for Multi-AZ RDS."
  type        = number
  default     = 2
  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3."
  }
}

variable "domain_name" {
  description = "Public DNS name for the ALB (e.g. copilot.example.com). Must already exist in Route 53 with an ACM cert."
  type        = string
  default     = "copilot.PLACEHOLDER.example.com"
}

variable "acm_certificate_arn" {
  description = "ARN of the validated ACM certificate for domain_name. Created out-of-band because of DNS validation chicken-and-egg."
  type        = string
  default     = "arn:aws:acm:us-east-1:000000000000:certificate/PLACEHOLDER"
}

variable "container_image" {
  description = "Full image URI to deploy. Built and pushed by CI to ECR before terraform apply."
  type        = string
  default     = "PLACEHOLDER.dkr.ecr.us-east-1.amazonaws.com/clinical-copilot:latest"
}

variable "task_cpu" {
  description = "Fargate task CPU (in CPU units). 256, 512, 1024, 2048."
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Fargate task memory in MB. Must be valid for the cpu value above."
  type        = number
  default     = 1024
}

variable "service_desired_count" {
  description = "Number of Fargate tasks. 2 is the minimum for HA across AZs."
  type        = number
  default     = 2
}

variable "db_instance_class" {
  description = "RDS instance class. db.t4g.medium is the smallest practical Multi-AZ size."
  type        = string
  default     = "db.t4g.medium"
}

variable "db_allocated_storage_gb" {
  description = "RDS allocated storage in GB. gp3 with autoscaling enabled."
  type        = number
  default     = 50
}

variable "db_backup_retention_days" {
  description = "Days of automated backups to keep. HIPAA-friendly: 35 (max for non-Aurora RDS) for short-term + manual archival to S3 Object Lock for the 6-year retention."
  type        = number
  default     = 35
}

variable "log_retention_days" {
  description = "CloudWatch log retention. Compliance baseline retention is 6 years (2192 days) — but most teams ship to S3 Glacier for the long tail and keep a 90-day hot window in CloudWatch."
  type        = number
  default     = 90
}

variable "anthropic_model" {
  description = "Anthropic model id passed to the agent via env."
  type        = string
  default     = "claude-opus-4-7"
}

variable "daily_token_budget" {
  description = "Per-user, per-day token cap enforced by agent/budget.py."
  type        = number
  default     = 200000
}

variable "alarm_notification_email" {
  description = "Email subscribed to the SNS topic for CloudWatch alarms."
  type        = string
  default     = "PLACEHOLDER-oncall@example.com"
}
