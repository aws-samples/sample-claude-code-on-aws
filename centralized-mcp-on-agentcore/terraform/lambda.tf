data "archive_file" "policy_lookup_lambda" {
  type        = "zip"
  source_file = "${path.module}/lambda/policy_lookup.py"
  output_path = "${path.module}/.build/policy_lookup.zip"
}

data "archive_file" "claims_lambda" {
  type        = "zip"
  source_file = "${path.module}/lambda/claims.py"
  output_path = "${path.module}/.build/claims.zip"
}

resource "aws_lambda_function" "policy_lookup" {
  function_name    = "${var.demo_prefix}-policy-lookup"
  description      = "Insurance policy lookup tool for AgentCore Gateway demo"
  role             = aws_iam_role.lambda_execution.arn
  handler          = "policy_lookup.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 128
  filename         = data.archive_file.policy_lookup_lambda.output_path
  source_code_hash = data.archive_file.policy_lookup_lambda.output_base64sha256

  tags = {
    "auto-delete" = "no"
  }
}

resource "aws_lambda_function" "claims" {
  function_name    = "${var.demo_prefix}-claims"
  description      = "Insurance claims data tool for AgentCore Gateway demo (RESTRICTED)"
  role             = aws_iam_role.lambda_execution.arn
  handler          = "claims.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 128
  filename         = data.archive_file.claims_lambda.output_path
  source_code_hash = data.archive_file.claims_lambda.output_base64sha256

  environment {
    variables = {
      CONTEXTUAL_USER       = var.contextual_user
      CONTEXTUAL_MAX_AMOUNT = tostring(var.contextual_max_amount)
    }
  }

  tags = {
    "auto-delete" = "no"
  }
}
