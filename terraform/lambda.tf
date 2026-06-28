resource "aws_ecr_repository" "lambdas" {
  name                 = "${var.project}-lambdas"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "${var.project}-lambdas" }
}

resource "aws_ecr_lifecycle_policy" "lambdas" {
  repository = aws_ecr_repository.lambdas.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "app_logs" {
  name              = "/cloudops/app-logs"
  retention_in_days = 14

  tags = { Name = "${var.project}-app-logs" }
}

resource "aws_lambda_function" "ingestion" {
  function_name = "${var.project}-ingestion"
  description   = "Processes CloudWatch log events, runs Bedrock AI analysis, stores incidents"

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambdas.repository_url}:ingestion-latest"

  image_config {
    command = ["ingestion.handler.lambda_handler"]
  }

  role        = aws_iam_role.lambda_ingestion.arn
  timeout     = 60
  memory_size = 256

  environment {
    variables = {
      DYNAMODB_TABLE   = aws_dynamodb_table.incidents.name
      SNS_TOPIC_ARN    = aws_sns_topic.alerts.arn
      AWS_REGION_NAME  = var.aws_region
      BEDROCK_MODEL_ID = "amazon.nova-micro-v1:0"
    }
  }

  vpc_config {
    subnet_ids         = [aws_subnet.private.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  tags = { Name = "${var.project}-ingestion" }

  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_cloudwatch_log_group" "ingestion_logs" {
  name              = "/aws/lambda/${aws_lambda_function.ingestion.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_subscription_filter" "error_filter" {
  name            = "${var.project}-error-filter"
  log_group_name  = aws_cloudwatch_log_group.app_logs.name
  filter_pattern  = "?ERROR ?CRITICAL"
  destination_arn = aws_lambda_function.ingestion.arn

  depends_on = [aws_lambda_permission.allow_cloudwatch]
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowCloudWatchLogs"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "logs.amazonaws.com"
  source_arn    = "${aws_cloudwatch_log_group.app_logs.arn}:*"
}

resource "aws_lambda_function" "api" {
  function_name = "${var.project}-api"
  description   = "REST API handler for incident CRUD operations"

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambdas.repository_url}:api-latest"

  image_config {
    command = ["api.handler.lambda_handler"]
  }

  role        = aws_iam_role.lambda_api.arn
  timeout     = 30
  memory_size = 256

  environment {
    variables = {
      DYNAMODB_TABLE  = aws_dynamodb_table.incidents.name
      AWS_REGION_NAME = var.aws_region
      SEVERITY_GSI    = "severity-index"
    }
  }

  vpc_config {
    subnet_ids         = [aws_subnet.private.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  tags = { Name = "${var.project}-api" }

  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_cloudwatch_log_group" "api_logs" {
  name              = "/aws/lambda/${aws_lambda_function.api.function_name}"
  retention_in_days = 14
}

resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.incidents.execution_arn}/*/*"
}

resource "aws_lambda_function" "guardduty_forwarder" {
  function_name = "${var.project}-guardduty-forwarder"
  description   = "Formats GuardDuty findings and sends SNS alert"

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambdas.repository_url}:guardduty-latest"

  image_config {
    command = ["guardduty.handler.lambda_handler"]
  }

  role        = aws_iam_role.lambda_guardduty.arn
  timeout     = 30
  memory_size = 128

  environment {
    variables = {
      SNS_TOPIC_ARN = aws_sns_topic.alerts.arn
    }
  }

  tags = { Name = "${var.project}-guardduty-forwarder" }

  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_cloudwatch_log_group" "guardduty_forwarder_logs" {
  name              = "/aws/lambda/${aws_lambda_function.guardduty_forwarder.function_name}"
  retention_in_days = 14
}