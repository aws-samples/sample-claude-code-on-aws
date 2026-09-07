output "policy_lookup_lambda_arn" {
  description = "Policy Lookup Lambda function ARN"
  value       = aws_lambda_function.policy_lookup.arn
}

output "policy_lookup_lambda_name" {
  description = "Policy Lookup Lambda function name"
  value       = aws_lambda_function.policy_lookup.function_name
}

output "claims_lambda_arn" {
  description = "Claims Lambda function ARN"
  value       = aws_lambda_function.claims.arn
}

output "claims_lambda_name" {
  description = "Claims Lambda function name"
  value       = aws_lambda_function.claims.function_name
}

output "lambda_role_name" {
  description = "Lambda execution IAM role name"
  value       = aws_iam_role.lambda_execution.name
}

output "gateway_role_arn" {
  description = "AgentCore Gateway IAM role ARN"
  value       = aws_iam_role.gateway.arn
}
