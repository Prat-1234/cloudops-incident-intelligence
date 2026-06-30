import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns = boto3.client("sns")
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]


def _severity_label(score):
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


def lambda_handler(event, context):
    logger.info("GuardDuty finding: %s", json.dumps(event))

    detail = event.get("detail", {})
    finding_id = detail.get("id", "unknown")
    finding_type = detail.get("type", "Unknown")
    title = detail.get("title", "GuardDuty Finding")
    description = detail.get("description", "No description available")
    severity_raw = float(detail.get("severity", 0))
    severity = _severity_label(severity_raw)
    region = detail.get("region", os.environ.get("AWS_REGION", "us-east-1"))
    account_id = detail.get("accountId", "unknown")
    updated_at = detail.get("updatedAt", "unknown")

    if severity_raw < 4.0:
        logger.info("Suppressing LOW severity finding %s", finding_id)
        return {"statusCode": 200, "body": "suppressed-low-severity"}

    subject = f"[{severity}] GuardDuty: {finding_type[:60]}"
    message = (
        f"GUARDDUTY SECURITY FINDING\n\n"
        f"Severity:    {severity} ({severity_raw})\n"
        f"Type:        {finding_type}\n"
        f"Title:       {title}\n"
        f"Account:     {account_id}\n"
        f"Region:      {region}\n"
        f"Finding ID:  {finding_id}\n"
        f"Updated:     {updated_at}\n\n"
        f"DESCRIPTION:\n{description}\n\n"
        f"VIEW IN CONSOLE:\n"
        f"https://console.aws.amazon.com/guardduty/home?region={region}#/findings"
        f"?macros=current&fId={finding_id}\n"
    )

    try:
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
        logger.info("SNS alert sent for finding %s", finding_id)
    except ClientError as e:
        logger.error("SNS publish failed: %s", e)
        raise

    return {"statusCode": 200, "body": "alert-sent"}
