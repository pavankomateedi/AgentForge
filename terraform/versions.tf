terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state — uncomment and fill in once an S3 bucket + DynamoDB
  # lock table exist. Until then, terraform plan against this
  # blueprint runs with local state, which is fine for validation.
  #
  # backend "s3" {
  #   bucket         = "agentforge-tfstate-<accountid>"
  #   key            = "clinical-copilot/prod.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   kms_key_id     = "alias/tfstate"
  #   dynamodb_table = "agentforge-tfstate-locks"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project       = "clinical-copilot"
      Environment   = var.environment
      ManagedBy     = "terraform"
      DataClass     = "PHI"
      Compliance    = "HIPAA"
      Owner         = var.owner_email
    }
  }
}
