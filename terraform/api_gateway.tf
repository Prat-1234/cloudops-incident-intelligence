resource "aws_api_gateway_rest_api" "incidents" {
  name        = "${var.project}-api"
  description = "CloudOps Incident Intelligence REST API"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = { Name = "${var.project}-api" }
}

# ── /incidents ─────────────────────────────────────────
resource "aws_api_gateway_resource" "incidents" {
  rest_api_id = aws_api_gateway_rest_api.incidents.id
  parent_id   = aws_api_gateway_rest_api.incidents.root_resource_id
  path_part   = "incidents"
}

resource "aws_api_gateway_method" "get_incidents" {
  rest_api_id   = aws_api_gateway_rest_api.incidents.id
  resource_id   = aws_api_gateway_resource.incidents.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "get_incidents" {
  rest_api_id             = aws_api_gateway_rest_api.incidents.id
  resource_id             = aws_api_gateway_resource.incidents.id
  http_method             = aws_api_gateway_method.get_incidents.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

# ── /incidents/{id} ────────────────────────────────────
resource "aws_api_gateway_resource" "incident_id" {
  rest_api_id = aws_api_gateway_rest_api.incidents.id
  parent_id   = aws_api_gateway_resource.incidents.id
  path_part   = "{id}"
}

resource "aws_api_gateway_method" "get_incident" {
  rest_api_id   = aws_api_gateway_rest_api.incidents.id
  resource_id   = aws_api_gateway_resource.incident_id.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "get_incident" {
  rest_api_id             = aws_api_gateway_rest_api.incidents.id
  resource_id             = aws_api_gateway_resource.incident_id.id
  http_method             = aws_api_gateway_method.get_incident.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

resource "aws_api_gateway_method" "delete_incident" {
  rest_api_id   = aws_api_gateway_rest_api.incidents.id
  resource_id   = aws_api_gateway_resource.incident_id.id
  http_method   = "DELETE"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "delete_incident" {
  rest_api_id             = aws_api_gateway_rest_api.incidents.id
  resource_id             = aws_api_gateway_resource.incident_id.id
  http_method             = aws_api_gateway_method.delete_incident.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

# ── /incidents/simulate ────────────────────────────────
resource "aws_api_gateway_resource" "simulate" {
  rest_api_id = aws_api_gateway_rest_api.incidents.id
  parent_id   = aws_api_gateway_resource.incidents.id
  path_part   = "simulate"
}

resource "aws_api_gateway_method" "simulate" {
  rest_api_id   = aws_api_gateway_rest_api.incidents.id
  resource_id   = aws_api_gateway_resource.simulate.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "simulate" {
  rest_api_id             = aws_api_gateway_rest_api.incidents.id
  resource_id             = aws_api_gateway_resource.simulate.id
  http_method             = aws_api_gateway_method.simulate.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

# ── CORS OPTIONS on /incidents ─────────────────────────
resource "aws_api_gateway_method" "options_incidents" {
  rest_api_id   = aws_api_gateway_rest_api.incidents.id
  resource_id   = aws_api_gateway_resource.incidents.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_incidents" {
  rest_api_id = aws_api_gateway_rest_api.incidents.id
  resource_id = aws_api_gateway_resource.incidents.id
  http_method = "OPTIONS"
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
  depends_on = [aws_api_gateway_method.options_incidents]
}

resource "aws_api_gateway_method_response" "options_incidents" {
  rest_api_id = aws_api_gateway_rest_api.incidents.id
  resource_id = aws_api_gateway_resource.incidents.id
  http_method = "OPTIONS"
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "options_incidents" {
  rest_api_id = aws_api_gateway_rest_api.incidents.id
  resource_id = aws_api_gateway_resource.incidents.id
  http_method = "OPTIONS"
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,DELETE,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_integration.options_incidents]
}

# ── Deployment & Stage ─────────────────────────────────
resource "aws_api_gateway_deployment" "incidents" {
  rest_api_id = aws_api_gateway_rest_api.incidents.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_integration.get_incidents,
      aws_api_gateway_integration.get_incident,
      aws_api_gateway_integration.delete_incident,
      aws_api_gateway_integration.simulate,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.incidents.id
  deployment_id = aws_api_gateway_deployment.incidents.id
  stage_name    = "prod"

  tags = { Name = "${var.project}-api-prod" }
}