# RDS PostgreSQL Multi-AZ. Encryption is non-optional (customer-managed
# KMS key); deletion protection is on; final snapshot mandatory; minor
# version upgrades auto-applied during the maintenance window.

resource "random_password" "db" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "db_password" {
  name        = "${local.name_prefix}-db-password"
  description = "RDS master password — rotated by Lambda (not yet wired)."
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnets"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${local.name_prefix}-db-subnets" }
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${local.name_prefix}-pg16"
  family = "postgres16"

  # Force TLS for every connection.
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  # Log all DDL + slow queries to CloudWatch — feeds the audit trail.
  parameter {
    name  = "log_statement"
    value = "ddl"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # milliseconds
  }
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name_prefix}-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  # Storage
  allocated_storage     = var.db_allocated_storage_gb
  max_allocated_storage = var.db_allocated_storage_gb * 4 # autoscale up to 4x
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.data.arn

  db_name  = "clinical_copilot"
  username = "ccp_admin"
  password = random_password.db.result

  # Network
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false

  # HA + DR
  multi_az                            = true
  backup_retention_period             = var.db_backup_retention_days
  backup_window                       = "08:00-09:00"
  maintenance_window                  = "sun:09:00-sun:11:00"
  deletion_protection                 = true
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${local.name_prefix}-db-final-snapshot"
  copy_tags_to_snapshot               = true
  iam_database_authentication_enabled = true

  parameter_group_name = aws_db_parameter_group.postgres.name

  # Monitoring
  performance_insights_enabled          = true
  performance_insights_kms_key_id       = aws_kms_key.data.arn
  performance_insights_retention_period = 7
  monitoring_interval                   = 60
  monitoring_role_arn                   = aws_iam_role.rds_monitoring.arn
  enabled_cloudwatch_logs_exports       = ["postgresql", "upgrade"]

  apply_immediately       = false
  auto_minor_version_upgrade = true
}

# Enhanced monitoring role for RDS.
data "aws_iam_policy_document" "rds_monitoring_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rds_monitoring" {
  name               = "${local.name_prefix}-rds-monitoring"
  assume_role_policy = data.aws_iam_policy_document.rds_monitoring_assume.json
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
