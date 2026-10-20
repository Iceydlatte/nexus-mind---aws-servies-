"""Authenticated Nexus Mind data and report-email API."""

import json
import os
import re
import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import boto3
from botocore.config import Config
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["USER_DATA_TABLE"])
ses = boto3.client("sesv2")
s3 = boto3.client("s3")
bedrock_runtime = boto3.client(
    "bedrock-runtime",
    config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
)
data_bucket = os.environ["APP_DATA_BUCKET"]
bedrock_model_id = os.environ["BEDROCK_MODEL_ID"]
MAX_DATA_BYTES = 300_000
ALLOWED_DATA_KEYS = {"activities", "goals", "tasks", "habits", "reflections", "preferences"}


def response(status, payload):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
        "body": json.dumps(payload, separators=(",", ":")),
    }


def request_identity(event):
    authorizer = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {})
    claims = authorizer.get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        raise ValueError("Sign in is required.")
    return user_id, claims


def parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raise ValueError("Encoded request bodies are not supported.")
    if len(raw.encode("utf-8")) > MAX_DATA_BYTES:
        raise OverflowError("Your saved data is too large. Export it and remove older records.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON.") from exc


def validate_data(data):
    if not isinstance(data, dict) or set(data) - ALLOWED_DATA_KEYS:
        raise ValueError("The saved data format is not supported.")
    for key in ("activities", "goals", "tasks", "habits", "reflections"):
        if key in data and (not isinstance(data[key], list) or len(data[key]) > 2000):
            raise ValueError(f"{key} must be a list containing at most 2,000 items.")
    if "preferences" in data and not isinstance(data["preferences"], dict):
        raise ValueError("preferences must be an object.")
    if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > MAX_DATA_BYTES:
        raise OverflowError("Your saved data is too large. Export it and remove older records.")


def to_dynamodb(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [to_dynamodb(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dynamodb(item) for key, item in value.items()}
    return value


def from_dynamodb(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, list):
        return [from_dynamodb(item) for item in value]
    if isinstance(value, dict):
        return {key: from_dynamodb(item) for key, item in value.items()}
    return value


def email_report(user_id, claims, body):
    email = claims.get("email", "")
    if claims.get("email_verified", "false").lower() != "true" or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return response(403, {"error": "Verify your account email before sending a report."})
    report = body.get("report")
    if not isinstance(report, dict):
        return response(400, {"error": "Report data is required."})
    labels = {
        "days": "Days summarized",
        "avgProductivity": "Average illustrative score",
        "studyMinutes": "Study minutes",
        "entertainmentMinutes": "Entertainment minutes",
        "tasksCompleted": "Tasks completed",
        "tasksPlanned": "Tasks planned",
    }
    lines = ["Your Nexus Mind weekly summary", "", "This report was requested from your signed-in Nexus Mind account.", "These are descriptive app records, not health or behavioral advice.", ""]
    for key, label in labels.items():
        value = report.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return response(400, {"error": "Report values must be numeric."})
        lines.append(f"{label}: {value}")
    now_dt = datetime.now(timezone.utc)
    now = int(now_dt.timestamp())
    try:
        table.update_item(
            Key={"userId": user_id, "recordType": "REPORT_LIMIT"},
            UpdateExpression="SET expiresAt = :expires",
            ConditionExpression="attribute_not_exists(expiresAt) OR expiresAt < :now",
            ExpressionAttributeValues={":expires": now + 60, ":now": now},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return response(429, {"error": "Please wait one minute before sending another report."})
        raise
    summary = {key: report.get(key, 0) for key in labels}
    report_record = {
        "createdAt": now_dt.isoformat(),
        "userId": user_id,
        "summary": summary,
    }
    report_key = f"reports/{user_id}/{now}-{now_dt.microsecond}.json"
    try:
        s3.put_object(
            Bucket=data_bucket,
            Key=report_key,
            Body=json.dumps(report_record, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        ses.send_email(
            FromEmailAddress=os.environ["SES_SENDER_EMAIL"],
            Destination={"ToAddresses": [email]},
            Content={"Simple": {
                "Subject": {"Data": "Your Nexus Mind weekly summary", "Charset": "UTF-8"},
                "Body": {"Text": {"Data": "\n".join(lines), "Charset": "UTF-8"}},
            }},
        )
    except ClientError as exc:
        if exc.operation_name == "SendEmail":
            return response(502, {"error": "Amazon SES could not send the report. Check SES identity verification and sandbox access."})
        raise
    return response(200, {"message": "The report was saved to your private AWS storage and sent to your verified account email."})


def synthetic_activities():
    result = s3.get_object(Bucket=data_bucket, Key="synthetic/activities.csv")
    rows = csv.DictReader(io.TextIOWrapper(result["Body"], encoding="utf-8"))
    source = list(rows)[:30]
    today = date.today()
    activities = []
    for index, row in enumerate(source):
        study = int(row["study_minutes"])
        entertainment = int(row["entertainment_minutes"])
        completed = int(row["tasks_completed"])
        sleep = float(row["sleep_duration"])
        switches = int(row["context_switches"])
        score = max(10, min(98, round(27 + study * 0.16 + completed * 4 + sleep * 1.4 - entertainment * 0.055 - switches * 0.55)))
        activities.append({
            "date": (today - timedelta(days=len(source) - index - 1)).isoformat(),
            "study_minutes": study,
            "entertainment_minutes": entertainment,
            "youtube_minutes": int(row["youtube_minutes"]),
            "screen_time_minutes": int(row["screen_time_minutes"]),
            "focus_sessions": int(row["focus_sessions"]),
            "tasks_completed": completed,
            "tasks_planned": int(row["tasks_planned"]),
            "sleep_duration": sleep,
            "context_switches": switches,
            "score": score,
            "source": "Synthetic sample",
        })
    return response(200, {"activities": activities})


def delete_user_reports(user_id):
    prefix = f"reports/{user_id}/"
    page = s3.get_paginator("list_objects_v2")
    for result in page.paginate(Bucket=data_bucket, Prefix=prefix):
        objects = [{"Key": item["Key"]} for item in result.get("Contents", [])]
        if objects:
            s3.delete_objects(Bucket=data_bucket, Delete={"Objects": objects, "Quiet": True})


def save_report(user_id, body):
    report = body.get("report")
    expected = {"title", "days", "avgProductivity", "studyMinutes", "entertainmentMinutes", "tasksCompleted", "tasksPlanned", "note"}
    if not isinstance(report, dict) or set(report) - expected:
        return response(400, {"error": "Report data is not in the supported format."})
    for key in ("days", "avgProductivity", "studyMinutes", "entertainmentMinutes", "tasksCompleted", "tasksPlanned"):
        value = report.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return response(400, {"error": "Report values must be non-negative numbers."})
    created_at = datetime.now(timezone.utc)
    key = f"reports/{user_id}/{int(created_at.timestamp())}-{created_at.microsecond}-download.json"
    s3.put_object(
        Bucket=data_bucket,
        Key=key,
        Body=json.dumps({"createdAt": created_at.isoformat(), "userId": user_id, "report": report}, separators=(",", ":")).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    return response(200, {"message": "Report saved to your private AWS storage."})


def task_summary(tasks):
    pending = [task.get("name", "Untitled task") for task in tasks if not task.get("done")]
    completed = [task.get("name", "Untitled task") for task in tasks if task.get("done")]
    if not tasks:
        return "Your task list is empty. Say ‘add a task’ and I’ll help you create one."
    parts = [f"You have {len(pending)} pending and {len(completed)} completed task(s)."]
    if pending:
        parts.append("Pending: " + "; ".join(pending[:8]) + ("; and more" if len(pending) > 8 else "."))
    if completed:
        parts.append("Completed: " + "; ".join(completed[:5]) + ("; and more" if len(completed) > 5 else "."))
    return " ".join(parts)


def apply_assistant_tool(name, arguments, tasks, data, changed):
    if name == "list_tasks":
        return {"tasks": tasks, "summary": task_summary(tasks)}, changed
    if name == "add_task":
        task_name = arguments.get("name")
        if not isinstance(task_name, str) or not task_name.strip() or len(task_name.strip()) > 180:
            return {"error": "Task names must be 1 to 180 characters."}, changed
        if len(tasks) >= 2000:
            return {"error": "The task list is full."}, changed
        tasks.append({"name": task_name.strip(), "due": "", "done": False})
        data["tasks"] = tasks
        return {"ok": True, "added": task_name.strip(), "summary": task_summary(tasks)}, True
    if name == "set_task_status":
        task_name = arguments.get("name")
        done = arguments.get("done")
        if not isinstance(task_name, str) or not task_name.strip() or not isinstance(done, bool):
            return {"error": "A task name and boolean status are required."}, changed
        needle = task_name.strip().casefold()
        exact = [task for task in tasks if str(task.get("name", "")).casefold() == needle]
        matches = exact or [task for task in tasks if needle in str(task.get("name", "")).casefold()]
        if len(matches) > 1:
            return {"error": "Multiple tasks matched.", "matches": [task.get("name", "Untitled task") for task in matches[:5]]}, changed
        if not matches:
            return {"error": f'No task matched "{task_name.strip()}".'}, changed
        matches[0]["done"] = done
        data["tasks"] = tasks
        return {"ok": True, "task": matches[0], "summary": task_summary(tasks)}, True
    return {"error": "Unknown task tool."}, changed


def assistant_chat(user_id, body):
    text = body.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return response(400, {"error": "Enter a message of 1 to 4,000 characters."})

    item = table.get_item(Key={"userId": user_id, "recordType": "APP_DATA"}, ConsistentRead=True).get("Item")
    data = from_dynamodb(item.get("data")) if item else {}
    if not isinstance(data, dict):
        data = {}
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
    data["tasks"] = tasks
    version = int(item.get("version", 0)) if item else 0
    history_item = table.get_item(Key={"userId": user_id, "recordType": "CHAT_HISTORY"}).get("Item") or {}
    history = from_dynamodb(history_item.get("messages", []))
    if not isinstance(history, list):
        history = []
    messages = [message for message in history[-12:] if isinstance(message, dict)]
    messages.append({"role": "user", "content": [{"text": text.strip()}]})

    system = [{
        "text": (
            "You are Nexus Mind, a warm and practical productivity assistant. "
            "Answer naturally and concisely, like a helpful ChatGPT-style assistant. "
            "You can discuss planning, study habits, focus, and the user's tasks. "
            "Use task tools when the user asks to list, add, complete, or reopen a task. "
            "Never claim a task changed unless a tool confirms it. "
            f"Here is the user's current task list as JSON: {json.dumps(tasks, ensure_ascii=False)}"
        )
    }]
    tools = {"tools": [{"toolSpec": {
        "name": "list_tasks",
        "description": "List the user's current tasks.",
        "inputSchema": {"json": {"type": "object", "properties": {}, "additionalProperties": False}},
    }}, {"toolSpec": {
        "name": "add_task",
        "description": "Add a new pending task.",
        "inputSchema": {"json": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    }}, {"toolSpec": {
        "name": "set_task_status",
        "description": "Mark one existing task complete or pending.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "name": {"type": "string"}, "done": {"type": "boolean"}
        }, "required": ["name", "done"]}},
    }}]}

    changed = False
    next_version = version
    tool_messages = []
    try:
        for _ in range(3):
            result = bedrock_runtime.converse(
                modelId=bedrock_model_id,
                system=system,
                messages=messages,
                inferenceConfig={"maxTokens": 700, "temperature": 0.6},
                toolConfig=tools,
            )
            assistant_message = result.get("output", {}).get("message", {})
            messages.append(assistant_message)
            if result.get("stopReason") != "tool_use":
                reply = " ".join(
                    block.get("text", "") for block in assistant_message.get("content", []) if block.get("text")
                ).strip()
                break
            results = []
            for block in assistant_message.get("content", []):
                tool_use = block.get("toolUse")
                if not tool_use:
                    continue
                tool_name = tool_use.get("name")
                tool_input = tool_use.get("input") or {}
                tool_result, changed = apply_assistant_tool(tool_name, tool_input, tasks, data, changed)
                results.append({"toolResult": {
                    "toolUseId": tool_use["toolUseId"],
                    "content": [{"text": json.dumps(tool_result, ensure_ascii=False)}],
                }})
            messages.append({"role": "user", "content": results})
        else:
            return response(502, {"error": "The assistant could not complete that request. Try again."})
    except bedrock_runtime.exceptions.ThrottlingException:
        return response(429, {"error": "The assistant is busy. Wait a moment and try again."})
    except bedrock_runtime.exceptions.AccessDeniedException:
        return response(503, {"error": "The AI assistant is not enabled for this AWS project yet."})
    except ClientError:
        return response(502, {"error": "The AI assistant could not process that message. Try again shortly."})

    if changed:
        validate_data(data)
        updated_at = datetime.now(timezone.utc).isoformat()
        next_version = version + 1
        new_item = {"userId": user_id, "recordType": "APP_DATA", "data": to_dynamodb(data), "updatedAt": updated_at, "version": next_version}
        try:
            condition = Attr("version").eq(version) if item else Attr("userId").not_exists()
            table.put_item(Item=new_item, ConditionExpression=condition)
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            return response(409, {"error": "Your tasks changed on another device. Reload the latest copy, then try again."})

    saved_messages = []
    for message in messages:
        if message.get("role") in {"user", "assistant"} and all("text" in block for block in message.get("content", [])):
            saved_messages.append(message)
    table.put_item(Item={
        "userId": user_id,
        "recordType": "CHAT_HISTORY",
        "messages": to_dynamodb(saved_messages[-12:]),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    })
    return response(200, {"reply": reply or "I’m ready to help.", "tasks": tasks, "version": next_version})


def handler(event, _context):
    try:
        method = event.get("requestContext", {}).get("http", {}).get("method", "")
        path = event.get("rawPath", "")

        if method == "GET" and path.endswith("/synthetic/activities"):
            return synthetic_activities()

        user_id, claims = request_identity(event)

        if method == "GET" and path.endswith("/me/data"):
            result = table.get_item(Key={"userId": user_id, "recordType": "APP_DATA"}, ConsistentRead=True)
            item = result.get("Item")
            return response(200, {
                "data": from_dynamodb(item.get("data")) if item else None,
                "updatedAt": item.get("updatedAt") if item else None,
                "version": int(item.get("version", 0)) if item else 0,
            })

        body = parse_body(event)
        if method == "PUT" and path.endswith("/me/data"):
            data = body.get("data")
            validate_data(data)
            expected_version = body.get("expectedVersion", 0)
            if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
                raise ValueError("expectedVersion must be a non-negative integer.")
            updated_at = datetime.now(timezone.utc).isoformat()
            condition = "attribute_not_exists(userId)" if expected_version == 0 else "#version = :expected"
            names = {"#version": "version"}
            values = {":data": to_dynamodb(data), ":updated": updated_at, ":next": expected_version + 1}
            if expected_version:
                values[":expected"] = expected_version
            try:
                table.update_item(
                    Key={"userId": user_id, "recordType": "APP_DATA"},
                    UpdateExpression="SET #data = :data, updatedAt = :updated, #version = :next",
                    ConditionExpression=condition,
                    ExpressionAttributeNames={**names, "#data": "data"},
                    ExpressionAttributeValues=values,
                )
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    return response(409, {"error": "A newer copy was saved from another device. Reload to get the latest version before saving again."})
                raise
            return response(200, {"message": "Cloud data saved.", "updatedAt": updated_at, "version": expected_version + 1})

        if method == "DELETE" and path.endswith("/me/data"):
            delete_user_reports(user_id)
            table.delete_item(Key={"userId": user_id, "recordType": "APP_DATA"})
            return response(200, {"message": "Cloud data deleted."})

        if method == "POST" and path.endswith("/me/email-report"):
            return email_report(user_id, claims, body)

        if method == "POST" and path.endswith("/me/assistant"):
            return assistant_chat(user_id, parse_body(event))

        if method == "POST" and path.endswith("/me/report"):
            return save_report(user_id, body)

        return response(404, {"error": "Route not found."})
    except OverflowError as exc:
        return response(413, {"error": str(exc)})
    except ValueError as exc:
        return response(400, {"error": str(exc)})
    except ClientError:
        return response(500, {"error": "A cloud data operation failed. Check the service logs."})
