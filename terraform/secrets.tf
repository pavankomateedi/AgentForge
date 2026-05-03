# Secrets Manager entries. Values are placeholders — set them out of
# band via `aws secretsmanager put-secret-value` after apply, then
# force a service redeploy. Terraform does NOT manage the cleartext
# values so they never enter state.

resource "aws_secretsmanager_secret" "anthropic_api_key" {
  name        = "${local.name_prefix}-anthropic-api-key"
  description = "Anthropic API key (sk-ant-...). Set via CLI after apply."
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "session_secret" {
  name        = "${local.name_prefix}-session-secret"
  description = "Cookie-signing secret. Generate with python -c 'import secrets; print(secrets.token_urlsafe(64))'."
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "langfuse_public_key" {
  name        = "${local.name_prefix}-langfuse-public-key"
  description = "Langfuse public key. Set via CLI after apply."
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "langfuse_secret_key" {
  name        = "${local.name_prefix}-langfuse-secret-key"
  description = "Langfuse secret key. Set via CLI after apply."
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = 7
}

# A note for the operator: after `terraform apply`, populate every
# placeholder secret value with a one-liner like:
#
#   aws secretsmanager put-secret-value \
#     --secret-id ccp-prod-anthropic-api-key \
#     --secret-string "sk-ant-..."
#
# Then force a fresh deploy so ECS pulls the new value:
#
#   aws ecs update-service --cluster ccp-prod-cluster \
#     --service ccp-prod-app --force-new-deployment
