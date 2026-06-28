resource "aws_guardduty_detector" "main" {
  enable = true

  datasources {
    s3_logs {
      enable = true
    }
    kubernetes {
      audit_logs { enable = false }
    }
    malware_protection {
      scan_ec2_instance_with_findings {
        ebs_volumes { enable = true }
      }
    }
  }

  tags = { Name = "${var.project}-guardduty" }
}

resource "aws_cloudwatch_event_rule" "guardduty_findings" {
  name        = "${var.project}-guardduty-findings"
  description = "Capture all GuardDuty findings"

  event_pattern = jsonencode({
    source      = ["aws.guardduty"]
    detail-type = ["GuardDuty Finding"]
  })

  tags = { Name = "${var.project}-guardduty-rule" }
}

resource "aws_cloudwatch_event_target" "guardduty_to_lambda" {
  rule      = aws_cloudwatch_event_rule.guardduty_findings.name
  target_id = "GuardDutyForwarderLambda"
  arn       = aws_lambda_function.guardduty_forwarder.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.guardduty_forwarder.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.guardduty_findings.arn
}

resource "aws_cloudwatch_event_rule" "simulate_schedule" {
  name                = "${var.project}-simulate-schedule"
  description         = "Inject synthetic log events every 5 min for live demo"
  schedule_expression = "rate(5 minutes)"

  tags = { Name = "${var.project}-simulate-schedule" }
}

resource "aws_cloudwatch_event_target" "simulate_to_lambda" {
  rule      = aws_cloudwatch_event_rule.simulate_schedule.name
  target_id = "SimulateLambda"
  arn       = aws_lambda_function.ingestion.arn

  input = jsonencode({
    source   = "scheduled-simulator"
    simulate = true
  })
}

resource "aws_lambda_permission" "allow_scheduler" {
  statement_id  = "AllowScheduledSimulator"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.simulate_schedule.arn
}