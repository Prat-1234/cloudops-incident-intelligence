data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "log_generator" {
  ami                    = data.aws_ami.amazon_linux_2023.id
  instance_type          = "t2.micro"
  subnet_id              = aws_subnet.private.id
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_log_generator.name

  user_data = base64encode(<<-EOF
    #!/bin/bash
    set -e
    dnf update -y
    dnf install -y python3 python3-pip
    pip3 install boto3
    cat > /home/ec2-user/log_generator.py << 'PYEOF'
    import boto3, time, random, datetime, socket

    LOG_GROUP  = "/cloudops/app-logs"
    LOG_STREAM = f"ec2-{socket.gethostname()}"
    REGION     = "us-east-1"

    client = boto3.client("logs", region_name=REGION)

    try:
        client.create_log_group(logGroupName=LOG_GROUP)
    except client.exceptions.ResourceAlreadyExistsException:
        pass
    try:
        client.create_log_stream(logGroupName=LOG_GROUP, logStreamName=LOG_STREAM)
    except client.exceptions.ResourceAlreadyExistsException:
        pass

    ERROR_TEMPLATES = [
        "ERROR: Database connection timeout after 30s — host=db.internal port=5432",
        "CRITICAL: Memory usage at 97% — OOM killer may be triggered",
        "ERROR: HTTP 503 from upstream payment-service after 3 retries",
        "CRITICAL: Disk usage at 98% on /dev/xvda — writes may fail",
        "ERROR: SSL certificate expires in 2 days for api.cloudops.internal",
        "ERROR: Failed to acquire distributed lock — timeout=5000ms",
        "CRITICAL: CPU usage 99% for 5 consecutive minutes",
        "ERROR: Redis connection refused — host=cache.internal port=6379",
    ]

    INFO_TEMPLATES = [
        "INFO: Request processed in 142ms — GET /api/v1/users",
        "INFO: Health check passed — all services nominal",
        "INFO: Scheduled job completed — duration=0.8s",
        "INFO: Cache hit ratio 94% — last 1000 requests",
    ]

    sequence_token = None

    while True:
        if random.random() < 0.25:
            message = random.choice(ERROR_TEMPLATES)
        else:
            message = random.choice(INFO_TEMPLATES)

        ts = int(datetime.datetime.utcnow().timestamp() * 1000)
        log_event = {"timestamp": ts, "message": message}

        kwargs = {
            "logGroupName":  LOG_GROUP,
            "logStreamName": LOG_STREAM,
            "logEvents":     [log_event]
        }
        if sequence_token:
            kwargs["sequenceToken"] = sequence_token

        try:
            response = client.put_log_events(**kwargs)
            sequence_token = response.get("nextSequenceToken")
            print(f"Logged: {message}")
        except Exception as e:
            print(f"CloudWatch error: {e}")
            sequence_token = None

        time.sleep(30)
    PYEOF

    nohup python3 /home/ec2-user/log_generator.py >> /var/log/log_generator.log 2>&1 &
    echo "Log generator started"
  EOF
  )

  tags = { Name = "${var.project}-log-generator" }
}