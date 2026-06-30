import base64
import gzip
import json
import logging
import os
import random
import uuid
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource(
    "dynamodb", region_name=os.environ["AWS_REGION_NAME"])
bedrock = boto3.client(
    "bedrock-runtime", region_name=os.environ["AWS_REGION_NAME"])
sns = boto3.client("sns", region_name=os.environ["AWS_REGION_NAME"])

TABLE = dynamodb.Table(os.environ["DYNAMODB_TABLE"])
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")

SIMULATED_ERRORS = [
    "ERROR: Database connection timeout after 30s — host=db.internal port=5432",
    "CRITICAL: Memory usage at 97% — OOM killer may be triggered",
    "ERROR: HTTP 503 from upstream payment-service after 3 retries",
    "CRITICAL: Disk usage at 98% on /dev/xvda — writes may fail",
    "ERROR: SSL certificate expires in 2 days for api.cloudops.internal",
    "ERROR: Failed to acquire distributed lock — timeout=5000ms",
    "CRITICAL: CPU usage 99% for 5 consecutive minutes",
    "ERROR: Redis connection refused — host=cache.internal port=6379",
]


def lambda_handler(event, context):
    logger.info("Event received: %s", json.dumps(event))
    log_messages = []

    if "awslogs" in event:
        log_messages = _decode_cloudwatch_logs(event["awslogs"]["data"])
    elif event.get("source") == "scheduled-simulator" or event.get("simulate"):
        log_messages = _generate_simulated_logs()
    else:
        logger.warning("Unknown event source: %s", event)
        return {"statusCode": 200, "body": "no-op"}

    results = []
    for message in log_messages:
        if not _is_error_log(message):
            continue
        try:
            incident = _process_log_message(message)
            results.append(incident["incident_id"])
        except Exception as e:
            logger.error("Failed to process message '%s': %s", message, e)

    return {"statusCode": 200, "body": json.dumps({"incidents_created": results})}


def _decode_cloudwatch_logs(encoded_data):
    compressed = base64.b64decode(encoded_data)
    decompressed = gzip.decompress(compressed)
    payload = json.loads(decompressed)
    return [event["message"] for event in payload.get("logEvents", [])]


def _generate_simulated_logs():
    return random.choices(SIMULATED_ERRORS, k=random.randint(1, 3))


def _is_error_log(message):
    return "ERROR" in message.upper() or "CRITICAL" in message.upper()


def _determine_severity(message):
    if "CRITICAL" in message.upper():
        return "CRITICAL"
    if "ERROR" in message.upper():
        return "HIGH"
    return "MEDIUM"


def _call_bedrock(log_message):
    prompt = f"""You are an expert SRE analysing a production log error.

Log message:
{log_message}

Respond with ONLY a JSON object with these exact keys:
{{
  "root_cause": "one sentence explaining the most likely root cause",
  "impact": "one sentence describing potential impact",
  "recommended_action": "one sentence with the most important immediate action",
  "estimated_resolution_time": "realistic estimate e.g. 5-10 minutes"
}}"""

    body = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "inferenceConfig": {"temperature": 0.1},
    }

    try:
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        raw = json.loads(response["body"].read())
        text = raw["output"]["message"]["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)

    except (ClientError, json.JSONDecodeError, KeyError) as e:
        logger.error("Bedrock call failed: %s", e)
        return _fallback_analysis(log_message)


def _fallback_analysis(log_message: str) -> dict:
    """
    Rule-based analysis used when Bedrock is unavailable
    (e.g. model access not yet granted, billing not configured).
    Keeps the dashboard populated with meaningful content.
    """
    ai_map = {
        "Database connection timeout": {
            "root_cause": "Database host unreachable — likely network partition or DB process crash",
            "impact": "All requests requiring DB reads/writes will fail with 500 errors",
            "recommended_action": "Check RDS health in AWS Console; failover to read replica if primary is down",
            "estimated_resolution_time": "5-15 minutes",
        },
        "Memory usage at 97%": {
            "root_cause": "Memory leak in application or sudden traffic spike exhausting heap",
            "impact": "OOM killer may terminate processes; service instability likely",
            "recommended_action": "Restart affected pods/instances; review heap dumps for memory leak",
            "estimated_resolution_time": "2-5 minutes for restart; root cause investigation 1-2 hours",
        },
        "HTTP 503": {
            "root_cause": "Upstream payment-service is overloaded or unhealthy — circuit breaker should trigger",
            "impact": "Payment processing failures; user checkouts will error",
            "recommended_action": "Check payment-service health endpoint; scale horizontally if CPU bound",
            "estimated_resolution_time": "10-20 minutes",
        },
        "Disk usage at 98%": {
            "root_cause": "Log files or temp data accumulating without rotation — disk nearly full",
            "impact": "Write operations will fail once disk is 100% full; possible data corruption",
            "recommended_action": "Run log rotation immediately; archive or delete old logs; add disk alarm",
            "estimated_resolution_time": "5-10 minutes",
        },
        "SSL certificate": {
            "root_cause": "TLS certificate approaching expiry — auto-renewal may have failed",
            "impact": "Browser HTTPS errors for all users in 2 days if not renewed",
            "recommended_action": "Trigger cert renewal via ACM or Let's Encrypt; verify auto-renewal config",
            "estimated_resolution_time": "15-30 minutes",
        },
        "distributed lock": {
            "root_cause": "Lock contention under high concurrency or a stuck process holding the lock",
            "impact": "Requests serialize or time out, increasing latency across the service",
            "recommended_action": "Inspect lock holder; force-release stale locks; review concurrency limits",
            "estimated_resolution_time": "10-15 minutes",
        },
        "CPU usage 99%": {
            "root_cause": "Compute-bound workload or runaway process consuming all available CPU",
            "impact": "Request latency spikes; health checks may start failing",
            "recommended_action": "Identify the hot process; scale out horizontally or vertically",
            "estimated_resolution_time": "10-20 minutes",
        },
        "Redis connection refused": {
            "root_cause": "Redis instance down, network ACL blocking traffic, or connection pool exhausted",
            "impact": "Cache misses spike; backend database load increases sharply",
            "recommended_action": "Check Redis instance health and security group rules; restart if unresponsive",
            "estimated_resolution_time": "5-10 minutes",
        },
        "Auth token validation failed": {
            "root_cause": "Expired signing key, clock skew, or misconfigured identity provider",
            "impact": "Legitimate users get rejected; potential service-wide login outage",
            "recommended_action": "Verify signing key rotation and IdP configuration; check system clock sync",
            "estimated_resolution_time": "15-30 minutes",
        },
        "Kafka consumer lag": {
            "root_cause": "Consumer group falling behind producer throughput — possible slow downstream processing",
            "impact": "Delayed order/event processing; data freshness SLA at risk",
            "recommended_action": "Scale consumer group; profile slow message handlers",
            "estimated_resolution_time": "20-30 minutes",
        },
    }

    for keyword, analysis in ai_map.items():
        if keyword.lower() in log_message.lower():
            return analysis

    return {
        "root_cause": "Unclassified error pattern — manual investigation required",
        "impact": "Service degradation possible; severity unconfirmed",
        "recommended_action": "Review raw log and escalate to on-call engineer",
        "estimated_resolution_time": "Unknown",
    }


def _process_log_message(message):
    incident_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()
    severity = _determine_severity(message)
    expires_at = int((now + timedelta(days=90)).timestamp())

    ai_analysis = _call_bedrock(message)

    item = {
        "incident_id":               incident_id,
        "timestamp":                 timestamp,
        "severity":                  severity,
        "raw_log":                   message,
        "root_cause":                ai_analysis.get("root_cause", ""),
        "impact":                    ai_analysis.get("impact", ""),
        "recommended_action":        ai_analysis.get("recommended_action", ""),
        "estimated_resolution_time": ai_analysis.get("estimated_resolution_time", ""),
        "status":                    "OPEN",
        "source":                    "cloudwatch-logs",
        "expires_at":                expires_at,
    }

    TABLE.put_item(Item=item)
    logger.info("Stored incident %s (severity=%s)", incident_id, severity)

    if severity == "CRITICAL":
        _send_sns_alert(item)

    return item


def _send_sns_alert(incident):
    subject = f"[CRITICAL] CloudOps Incident — {incident['incident_id'][:8]}"
    message = (
        f"CRITICAL INCIDENT DETECTED\n\n"
        f"Incident ID:   {incident['incident_id']}\n"
        f"Timestamp:     {incident['timestamp']}\n"
        f"Severity:      {incident['severity']}\n\n"
        f"LOG MESSAGE:\n{incident['raw_log']}\n\n"
        f"AI ROOT CAUSE ANALYSIS:\n"
        f"  Root Cause:   {incident['root_cause']}\n"
        f"  Impact:       {incident['impact']}\n"
        f"  Action:       {incident['recommended_action']}\n"
        f"  Est. Resolution: {incident['estimated_resolution_time']}\n\n"
        f"Status: OPEN — manual review required\n"
    )
    try:
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
        logger.info("SNS alert sent for incident %s", incident["incident_id"])
    except ClientError as e:
        logger.error("SNS publish failed: %s", e)
