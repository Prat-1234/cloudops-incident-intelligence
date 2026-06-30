import json
import logging
import os
import uuid
import random
from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource(
    "dynamodb", region_name=os.environ["AWS_REGION_NAME"])
TABLE = dynamodb.Table(os.environ["DYNAMODB_TABLE"])
GSI_NAME = os.environ.get("SEVERITY_GSI", "severity-index")

CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    "Content-Type":                 "application/json",
}

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
    method = event.get("httpMethod", "")
    path = event.get("path", "")
    params = event.get("pathParameters") or {}

    logger.info("API request: %s %s", method, path)

    try:
        if method == "OPTIONS":
            return _response(200, {})
        if method == "GET" and path.endswith("/incidents"):
            return _list_incidents(event)
        if method == "GET" and params.get("id"):
            return _get_incident(params["id"])
        if method == "DELETE" and params.get("id"):
            return _resolve_incident(params["id"])
        if method == "POST" and path.endswith("/simulate"):
            return _simulate_incident()
        return _response(404, {"error": f"No route for {method} {path}"})
    except Exception as e:
        logger.exception("Unhandled error: %s", e)
        return _response(500, {"error": "Internal server error"})


def _list_incidents(event):
    qs = event.get("queryStringParameters") or {}
    severity = qs.get("severity")
    status = qs.get("status")
    limit = min(int(qs.get("limit", 50)), 100)

    try:
        if severity:
            response = TABLE.query(
                IndexName=GSI_NAME,
                KeyConditionExpression=Key("severity").eq(severity.upper()),
                ScanIndexForward=False,
                Limit=limit,
            )
        else:
            scan_kwargs = {"Limit": limit}
            if status:
                scan_kwargs["FilterExpression"] = Attr(
                    "status").eq(status.upper())
            response = TABLE.scan(**scan_kwargs)

        items = response.get("Items", [])
        if not severity:
            items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return _response(200, {"incidents": items, "count": len(items)})
    except ClientError as e:
        logger.error("DynamoDB error: %s", e)
        return _response(500, {"error": "Failed to fetch incidents"})


def _get_incident(incident_id):
    try:
        response = TABLE.query(
            KeyConditionExpression=Key("incident_id").eq(incident_id),
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return _response(404, {"error": f"Incident {incident_id} not found"})
        return _response(200, items[0])
    except ClientError as e:
        logger.error("DynamoDB error: %s", e)
        return _response(500, {"error": "Failed to fetch incident"})


def _resolve_incident(incident_id):
    try:
        response = TABLE.query(
            KeyConditionExpression=Key("incident_id").eq(incident_id),
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return _response(404, {"error": f"Incident {incident_id} not found"})

        item = items[0]
        TABLE.update_item(
            Key={"incident_id": incident_id, "timestamp": item["timestamp"]},
            UpdateExpression="SET #s = :resolved, resolved_at = :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":resolved": "RESOLVED",
                ":now":      datetime.now(timezone.utc).isoformat(),
            },
        )
        return _response(200, {"message": f"Incident {incident_id} marked as RESOLVED"})
    except ClientError as e:
        logger.error("DynamoDB error: %s", e)
        return _response(500, {"error": "Failed to resolve incident"})


def _simulate_incident():
    message = random.choice(SIMULATED_ERRORS)
    incident_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    severity = "CRITICAL" if "CRITICAL" in message else "HIGH"

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
            "estimated_resolution_time": "2-5 minutes for restart; root cause 1-2 hours",
        },
        "HTTP 503": {
            "root_cause": "Upstream payment-service is overloaded or unhealthy",
            "impact": "Payment processing failures; user checkouts will error",
            "recommended_action": "Check payment-service health endpoint; scale horizontally if CPU bound",
            "estimated_resolution_time": "10-20 minutes",
        },
        "Disk usage at 98%": {
            "root_cause": "Log files accumulating without rotation — disk nearly full",
            "impact": "Write operations will fail once disk hits 100%; possible data corruption",
            "recommended_action": "Run log rotation immediately; archive old logs; add disk alarm",
            "estimated_resolution_time": "5-10 minutes",
        },
        "SSL certificate": {
            "root_cause": "TLS certificate approaching expiry — auto-renewal may have failed",
            "impact": "Browser HTTPS errors for all users in 2 days if not renewed",
            "recommended_action": "Trigger cert renewal via ACM; verify auto-renewal config",
            "estimated_resolution_time": "15-30 minutes",
        },
    }

    ai_analysis = {
        "root_cause": "Unclassified error — manual investigation required",
        "impact": "Service degradation possible",
        "recommended_action": "Review logs and escalate to on-call engineer",
        "estimated_resolution_time": "Unknown",
    }
    for keyword, analysis in ai_map.items():
        if keyword.lower() in message.lower():
            ai_analysis = analysis
            break

    item = {
        "incident_id":               incident_id,
        "timestamp":                 now.isoformat(),
        "severity":                  severity,
        "raw_log":                   message,
        "root_cause":                ai_analysis["root_cause"],
        "impact":                    ai_analysis["impact"],
        "recommended_action":        ai_analysis["recommended_action"],
        "estimated_resolution_time": ai_analysis["estimated_resolution_time"],
        "status":                    "OPEN",
        "source":                    "simulated",
        "expires_at":                int((now + timedelta(days=90)).timestamp()),
    }

    try:
        TABLE.put_item(Item=item)
        return _response(201, item)
    except ClientError as e:
        logger.error("DynamoDB error: %s", e)
        return _response(500, {"error": "Failed to create simulated incident"})


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers":    CORS_HEADERS,
        "body":       json.dumps(body, default=str),
    }
