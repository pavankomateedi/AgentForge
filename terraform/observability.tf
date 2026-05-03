# CloudWatch log groups (encrypted), metric filters that turn audit
# events into time-series metrics, and SNS-backed alarms on the ones
# that should page someone.

# ------------------------------------------------------------------
# Log groups
# ------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ccp/${var.environment}/app"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}

resource "aws_cloudwatch_log_group" "flow_logs" {
  name              = "/ccp/${var.environment}/vpc-flow-logs"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}

# ------------------------------------------------------------------
# Metric filters — pull structured audit events out of the app log.
# The agent emits JSON lines like {"event": "login_failed_bad_password", ...}.
# ------------------------------------------------------------------
resource "aws_cloudwatch_log_metric_filter" "login_failures" {
  name           = "${local.name_prefix}-login-failures"
  pattern        = "{ $.event = \"login_failed_bad_password\" || $.event = \"login_failed_locked\" }"
  log_group_name = aws_cloudwatch_log_group.app.name

  metric_transformation {
    name      = "LoginFailures"
    namespace = "ClinicalCopilot/${var.environment}"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "budget_exceeded" {
  name           = "${local.name_prefix}-budget-exceeded"
  pattern        = "{ $.event = \"budget_exceeded\" }"
  log_group_name = aws_cloudwatch_log_group.app.name

  metric_transformation {
    name      = "BudgetExceeded"
    namespace = "ClinicalCopilot/${var.environment}"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "emergency_access" {
  name           = "${local.name_prefix}-emergency-access"
  pattern        = "{ $.event = \"emergency_access\" }"
  log_group_name = aws_cloudwatch_log_group.app.name

  metric_transformation {
    name      = "EmergencyAccess"
    namespace = "ClinicalCopilot/${var.environment}"
    value     = "1"
    unit      = "Count"
  }
}

# ------------------------------------------------------------------
# SNS topic — alarms publish here; subscribers (email, PagerDuty)
# attach independently. Topic is encrypted; KMS key allows CloudWatch
# to publish.
# ------------------------------------------------------------------
resource "aws_sns_topic" "alarms" {
  name              = "${local.name_prefix}-alarms"
  kms_master_key_id = aws_kms_key.logs.id
}

resource "aws_sns_topic_subscription" "alarms_email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_notification_email
}

# ------------------------------------------------------------------
# Alarms
# ------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "login_failure_burst" {
  alarm_name          = "${local.name_prefix}-login-failure-burst"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "LoginFailures"
  namespace           = "ClinicalCopilot/${var.environment}"
  period              = 60
  statistic           = "Sum"
  threshold           = 20

  alarm_description = "More than 20 failed logins in a 1-minute window. Possible credential-stuffing or brute force."
  alarm_actions     = [aws_sns_topic.alarms.arn]
  ok_actions        = [aws_sns_topic.alarms.arn]
  treat_missing_data = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "emergency_access_any" {
  alarm_name          = "${local.name_prefix}-emergency-access"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "EmergencyAccess"
  namespace           = "ClinicalCopilot/${var.environment}"
  period              = 60
  statistic           = "Sum"
  threshold           = 1

  alarm_description = "Any break-glass access. Always paged, always reviewed."
  alarm_actions     = [aws_sns_topic.alarms.arn]
  treat_missing_data = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${local.name_prefix}-alb-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 10

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
  }

  alarm_description = "ALB observed >10 5xx responses/min for 2 mins. App is failing."
  alarm_actions     = [aws_sns_topic.alarms.arn]
  ok_actions        = [aws_sns_topic.alarms.arn]
  treat_missing_data = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "rds_high_cpu" {
  alarm_name          = "${local.name_prefix}-rds-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  alarm_description = "RDS CPU > 80% for 15 minutes. Investigate query load or upsize."
  alarm_actions     = [aws_sns_topic.alarms.arn]
  treat_missing_data = "notBreaching"
}
