# KMS keys, IAM roles, WAFv2. The KMS keys are split by data class so
# a key compromise blasts the smallest possible radius.

# ------------------------------------------------------------------
# KMS — separate keys for data, secrets, and logs.
# ------------------------------------------------------------------
resource "aws_kms_key" "data" {
  description             = "Encrypts RDS data at rest (clinical-copilot)"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  tags = { Name = "${local.name_prefix}-kms-data" }
}

resource "aws_kms_alias" "data" {
  name          = "alias/${local.name_prefix}-data"
  target_key_id = aws_kms_key.data.key_id
}

resource "aws_kms_key" "secrets" {
  description             = "Encrypts Secrets Manager entries (clinical-copilot)"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  tags = { Name = "${local.name_prefix}-kms-secrets" }
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${local.name_prefix}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

resource "aws_kms_key" "logs" {
  description             = "Encrypts CloudWatch Logs (clinical-copilot)"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  # CloudWatch Logs needs explicit permission to use the key.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRoot"
        Effect = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Principal = { Service = "logs.${var.aws_region}.amazonaws.com" }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*",
        ]
        Resource = "*"
      },
    ]
  })

  tags = { Name = "${local.name_prefix}-kms-logs" }
}

resource "aws_kms_alias" "logs" {
  name          = "alias/${local.name_prefix}-logs"
  target_key_id = aws_kms_key.logs.key_id
}

data "aws_caller_identity" "current" {}

# ------------------------------------------------------------------
# IAM — execution role (pulls image, writes logs), task role (reads
# secrets, writes app-level events). Split per AWS best practice so a
# task-role compromise can't pull arbitrary ECR images.
# ------------------------------------------------------------------
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${local.name_prefix}-task-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "task_execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow task execution role to read secrets it needs to inject as env vars.
data "aws_iam_policy_document" "task_execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.anthropic_api_key.arn,
      aws_secretsmanager_secret.session_secret.arn,
      aws_secretsmanager_secret.langfuse_public_key.arn,
      aws_secretsmanager_secret.langfuse_secret_key.arn,
      aws_secretsmanager_secret.db_password.arn,
    ]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.secrets.arn]
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_secrets.json
}

resource "aws_iam_role" "task" {
  name               = "${local.name_prefix}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# The application itself doesn't need any AWS APIs once running, but
# this role is the right place to add CloudWatch Logs put-event
# permissions if the app ever writes structured audit events to a
# dedicated log stream.
data "aws_iam_policy_document" "task_logs" {
  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.app.arn}:*"]
  }
}

resource "aws_iam_role_policy" "task_logs" {
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_logs.json
}

# IAM role for VPC flow logs.
data "aws_iam_policy_document" "flow_logs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "flow_logs" {
  name               = "${local.name_prefix}-flow-logs"
  assume_role_policy = data.aws_iam_policy_document.flow_logs_assume.json
}

data "aws_iam_policy_document" "flow_logs" {
  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["${aws_cloudwatch_log_group.flow_logs.arn}:*"]
  }
}

resource "aws_iam_role_policy" "flow_logs" {
  role   = aws_iam_role.flow_logs.id
  policy = data.aws_iam_policy_document.flow_logs.json
}

# ------------------------------------------------------------------
# WAFv2 — public web ACL bound to the ALB. Three managed rule groups
# + an explicit rate-limit on /auth/login.
# ------------------------------------------------------------------
resource "aws_wafv2_web_acl" "main" {
  name  = "${local.name_prefix}-waf"
  scope = "REGIONAL"

  default_action { allow {} }

  rule {
    name     = "AWS-CommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "common-rule-set"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWS-KnownBadInputs"
    priority = 2
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWS-SQLiRuleSet"
    priority = 3
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "sqli-rule-set"
      sampled_requests_enabled   = true
    }
  }

  # Belt-and-braces over auth.py's own 5/15 lockout.
  rule {
    name     = "RateLimit-Login"
    priority = 10
    action { block {} }
    statement {
      rate_based_statement {
        limit              = 100
        aggregate_key_type = "IP"
        scope_down_statement {
          byte_match_statement {
            search_string         = "/auth/login"
            field_to_match { uri_path {} }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
            positional_constraint = "STARTS_WITH"
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-limit-login"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.name_prefix}-waf"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "alb" {
  resource_arn = aws_lb.main.arn
  web_acl_arn  = aws_wafv2_web_acl.main.arn
}
