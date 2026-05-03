output "alb_dns_name" {
  description = "Public DNS name of the ALB. Point your Route 53 ALIAS at this."
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "ALB hosted-zone id, used for Route 53 ALIAS records."
  value       = aws_lb.main.zone_id
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (internal — only the Fargate service should connect)."
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "ecr_repository_url" {
  description = "ECR repo to push images to before each deploy."
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name. Useful for one-off ecs update-service force-new-deployment."
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.app.name
}

output "secrets_to_populate" {
  description = "ARNs of secrets that contain placeholder values — populate after first apply."
  value = {
    anthropic_api_key   = aws_secretsmanager_secret.anthropic_api_key.arn
    session_secret      = aws_secretsmanager_secret.session_secret.arn
    langfuse_public_key = aws_secretsmanager_secret.langfuse_public_key.arn
    langfuse_secret_key = aws_secretsmanager_secret.langfuse_secret_key.arn
  }
}

output "alarms_topic_arn" {
  description = "SNS topic for CloudWatch alarms. Subscribe PagerDuty / Slack here."
  value       = aws_sns_topic.alarms.arn
}
