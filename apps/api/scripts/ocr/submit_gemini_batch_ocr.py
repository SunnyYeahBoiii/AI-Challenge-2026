"""Submit and optionally monitor an OCR Gemini Batch inference job."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_PROJECT = "hcmc-aichallenge2026"
DEFAULT_BUCKET = "frameseeker-aic2026-assets"
DEFAULT_MODEL = "publishers/google/models/gemini-3.5-flash-lite"
SUCCEEDED_STATE = "JOB_STATE_SUCCEEDED"
TERMINAL_STATES = {
    SUCCEEDED_STATE,
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_PAUSED",
}


def normalized_model_name(model: str) -> str:
    """Return a publisher-qualified model name from a short or full model identifier."""
    return model if model.startswith("publishers/") else f"publishers/google/models/{model}"


def build_job_payload(
    *, display_name: str, input_uri: str, output_uri: str, model: str = DEFAULT_MODEL
) -> dict[str, Any]:
    """Build the Agent Platform BatchPredictionJob request body."""
    return {
        "displayName": display_name,
        "model": normalized_model_name(model),
        "inputConfig": {
            "instancesFormat": "jsonl",
            "gcsSource": {"uris": [input_uri]},
        },
        "outputConfig": {
            "predictionsFormat": "jsonl",
            "gcsDestination": {"outputUriPrefix": output_uri},
        },
    }


def get_access_token() -> str:
    """Get an access token from the active gcloud account."""
    gcloud = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if gcloud is None:
        raise RuntimeError(
            "Could not find gcloud. Install the Google Cloud CLI and add its bin directory to PATH."
        )
    completed = subprocess.run(
        [gcloud, "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    )
    token = completed.stdout.strip()
    if not token:
        raise RuntimeError("gcloud did not return an access token")
    return token


def send_request(
    *, method: str, url: str, access_token: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Call the Agent Platform REST API and return its JSON body."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        message = f"Agent Platform API returned HTTP {error.code}: {detail}"
        raise RuntimeError(message) from error
    except URLError as error:
        raise RuntimeError(f"Could not reach the Agent Platform API: {error.reason}") from error


def job_url(*, project: str, location: str, job_name: str | None = None) -> str:
    """Return the API URL for creating or reading a batch job."""
    endpoint_prefix = "" if location == "global" else f"{location}-"
    base = (
        f"https://{endpoint_prefix}aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{location}/batchPredictionJobs"
    )
    return f"https://aiplatform.googleapis.com/v1/{job_name}" if job_name else base


def wait_for_job(
    *, project: str, location: str, job_name: str, poll_interval: int
) -> dict[str, Any]:
    """Poll a BatchPredictionJob until it reaches a terminal state."""
    previous_state = ""
    while True:
        job = send_request(
            method="GET",
            url=job_url(project=project, location=location, job_name=job_name),
            access_token=get_access_token(),
        )
        state = str(job.get("state", "JOB_STATE_UNSPECIFIED"))
        if state != previous_state:
            print(f"Job state: {state}")
            previous_state = state
        if state in TERMINAL_STATES:
            return job
        time.sleep(poll_interval)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--location", default="global")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Gemini model ID, e.g. gemini-3.6-flash, or a full publisher model name.",
    )
    parser.add_argument("--display-name", default="gemini-ocr-l25")
    parser.add_argument(
        "--input-uri",
        default=f"gs://{DEFAULT_BUCKET}/ocr-batch/requests/L25/requests.jsonl",
    )
    parser.add_argument(
        "--output-uri",
        default=f"gs://{DEFAULT_BUCKET}/ocr-batch/output/L25/",
    )
    parser.add_argument("--wait", action="store_true", help="Poll until the job finishes.")
    parser.add_argument("--poll-interval", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    """Submit the Batch inference job and optionally wait for its completion."""
    args = parse_args()
    if args.poll_interval < 1:
        raise ValueError("--poll-interval must be positive")
    if not args.input_uri.startswith("gs://") or not args.output_uri.startswith("gs://"):
        raise ValueError("--input-uri and --output-uri must be gs:// URIs")

    job = send_request(
        method="POST",
        url=job_url(project=args.project, location=args.location),
        access_token=get_access_token(),
        payload=build_job_payload(
            display_name=args.display_name,
            input_uri=args.input_uri,
            output_uri=args.output_uri,
            model=args.model,
        ),
    )
    job_name = str(job["name"])
    print(f"Submitted Batch job: {job_name}")
    print(f"Output prefix: {args.output_uri}")

    if not args.wait:
        return

    completed_job = wait_for_job(
        project=args.project,
        location=args.location,
        job_name=job_name,
        poll_interval=args.poll_interval,
    )
    state = str(completed_job.get("state", "JOB_STATE_UNSPECIFIED"))
    if state != SUCCEEDED_STATE:
        print(json.dumps(completed_job.get("error", {}), ensure_ascii=False), file=sys.stderr)
        raise RuntimeError(f"Batch job ended in {state}")


if __name__ == "__main__":
    main()
