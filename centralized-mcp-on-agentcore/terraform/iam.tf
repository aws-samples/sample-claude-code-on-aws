data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_execution" {
  name               = "${var.demo_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- AgentCore Gateway role ---

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "gateway_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com", "bedrock-agentcore.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "${var.demo_prefix}-gateway-role"
  assume_role_policy = data.aws_iam_policy_document.gateway_assume_role.json
}

data "aws_iam_policy_document" "gateway_invoke_lambda" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.policy_lookup.arn,
      aws_lambda_function.claims.arn,
    ]
  }
}

resource "aws_iam_role_policy" "gateway_invoke_lambda" {
  name   = "invoke-lambda"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_invoke_lambda.json
}
