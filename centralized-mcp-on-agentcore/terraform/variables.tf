variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "demo_prefix" {
  description = "Naming prefix for all resources"
  type        = string
  default     = "agentcore-mcp-demo"
}

variable "contextual_user" {
  description = "Okta user email (JWT sub) for Cedar contextual control demo — this user gets a claim amount limit"
  type        = string
  default     = ""
}

variable "contextual_max_amount" {
  description = "Maximum claim amount visible to the contextual demo user (default: 100000)"
  type        = number
  default     = 100000
}
