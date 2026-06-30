FROM public.ecr.aws/lambda/python:3.12 AS base

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY lambdas/ingestion/ ${LAMBDA_TASK_ROOT}/ingestion/
COPY lambdas/api/       ${LAMBDA_TASK_ROOT}/api/
COPY lambdas/guardduty/ ${LAMBDA_TASK_ROOT}/guardduty/

FROM base AS ingestion
CMD ["ingestion.handler.lambda_handler"]

FROM base AS api
CMD ["api.handler.lambda_handler"]

FROM base AS guardduty
CMD ["guardduty.handler.lambda_handler"]