#!/usr/bin/env python3
"""
Create a Windows Jenkins AMI using SSM + EC2Launch v2.

Plan A: keep init.ps1 in SCM, read it locally, and send inline to SSM.
No SSH / WinRM / RDP is required.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

import boto3
from botocore.exceptions import ClientError


def log(msg: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bake a Windows Jenkins AMI via SSM.")
    p.add_argument(
        "--base_ami", required=True, help="Base Windows AMI ID (e.g., ami-xxxxxxxx)"
    )
    p.add_argument("--ami_name", required=True, help="Name for the new AMI")
    p.add_argument("--region", required=True, help="AWS region (e.g., us-east-1)")
    p.add_argument(
        "--subnet_id", required=True, help="Subnet ID to launch the builder in"
    )
    p.add_argument(
        "--security_group", required=True, help="Security group ID with egress to SSM"
    )
    p.add_argument(
        "--volume_size", type=int, default=80, help="Root EBS size (GiB). Default: 80"
    )
    p.add_argument(
        "--instance_type", default="m6i.large", help="Instance type. Default: m6i.large"
    )
    p.add_argument(
        "--script_path",
        default="./init.ps1",
        help="Path to init.ps1 to run inside the builder",
    )
    p.add_argument(
        "--iam_instance_profile_name",
        required=True,
        help="Instance profile name attached to the builder (must grant AmazonSSMManagedInstanceCore)",
    )
    p.add_argument(
        "--timeout_seconds",
        type=int,
        default=7200,
        help="Timeout seconds for SSM RunCommand. Default: 7200",
    )
    p.add_argument(
        "--wait_ssm_timeout",
        type=int,
        default=900,
        help="Max seconds to wait for SSM to come online. Default: 900",
    )
    p.add_argument(
        "--tags",
        default="",
        help='Optional JSON object of extra tags for the AMI (e.g., \'{"Project":"Jenkins"}\')',
    )
    return p.parse_args()


def ensure_file(path: str) -> str:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Script not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data = fh.read()
    # SSM inline payload limit is ~64 KB; keep a little headroom
    if len(data.encode("utf-8")) > 60_000:
        raise ValueError(
            f"{path} is too large to inline to SSM (>60KB). Consider a fetch-from-GitHub pattern."
        )
    return data


def wait_for_instance_running(ec2, instance_id: str) -> None:
    log(f"Waiting for instance {instance_id} to enter 'running'...")
    ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])
    log("Instance is running.")
    log("Waiting for instance status checks to pass...")
    ec2.get_waiter("instance_status_ok").wait(InstanceIds=[instance_id])
    log("Instance status checks OK.")


def wait_for_ssm_online(ssm, instance_id: str, timeout: int) -> None:
    log(f"Waiting for SSM to register and go Online (timeout {timeout}s)...")
    start = time.time()
    while True:
        try:
            resp = ssm.describe_instance_information(
                Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
            )
            lst = resp.get("InstanceInformationList", [])
            if lst and lst[0].get("PingStatus") == "Online":
                log("SSM is Online.")
                return
        except ClientError as e:
            log(
                f"describe_instance_information transient error: {e.response['Error']['Code']}"
            )
        if time.time() - start > timeout:
            raise TimeoutError("Timed out waiting for SSM to come Online.")
        time.sleep(10)


def run_ssm_powershell(
    ssm, instance_id: str, commands, timeout_seconds: int, comment: str
) -> None:
    if isinstance(commands, str):
        commands = [commands]
    log(f"Sending SSM RunCommand: {comment}")
    cmd = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunPowerShellScript",
        Parameters={"commands": commands},
        TimeoutSeconds=timeout_seconds,
        CloudWatchOutputConfig={"CloudWatchOutputEnabled": False},
        Comment=comment,
    )
    cmd_id = cmd["Command"]["CommandId"]
    while True:
        try:
            inv = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=instance_id)
            status = inv["Status"]
            if status in ("Success", "Failed", "Cancelled", "TimedOut"):
                if status != "Success":
                    stderr = (inv.get("StandardErrorContent") or "")[:1000]
                    raise RuntimeError(f"SSM command failed: {status}\n{stderr}")
                log("RunCommand succeeded.")
                return
        except ClientError as e:
            if e.response["Error"]["Code"] not in ("InvocationDoesNotExist",):
                raise
        time.sleep(5)


def main() -> None:
    args = parse_args()
    script = ensure_file(args.script_path)
    extra_tags = json.loads(args.tags) if args.tags else {}

    ec2 = boto3.client("ec2", region_name=args.region)
    ssm = boto3.client("ssm", region_name=args.region)

    # 1) Launch builder
    instance_name = f"{args.ami_name}-bake-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    log("Launching Windows builder instance...")
    resp = ec2.run_instances(
        ImageId=args.base_ami,
        InstanceType=args.instance_type,
        SubnetId=args.subnet_id,
        SecurityGroupIds=[args.security_group],
        IamInstanceProfile={"Name": args.iam_instance_profile_name},
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": instance_name},
                    {"Key": "BakedBy", "Value": "ami-jenkins-build-windows"},
                ],
            }
        ],
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": args.volume_size,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                    "Encrypted": True,
                },
            }
        ],
        UserData="""<powershell>
# Optional lightweight logging to help early troubleshooting
New-Item -ItemType Directory -Path C:\\BuildLogs -ErrorAction SilentlyContinue | Out-Null
</powershell>""",
    )
    instance_id = resp["Instances"][0]["InstanceId"]
    log(f"Launched builder instance: {instance_id}")

    try:
        # 2) Wait for running + SSM Online
        wait_for_instance_running(ec2, instance_id)
        wait_for_ssm_online(ssm, instance_id, args.wait_ssm_timeout)

        # 3) Run init.ps1 inline via SSM
        run_ssm_powershell(
            ssm,
            instance_id,
            script,
            args.timeout_seconds,
            comment="Run init.ps1 (inline from SCM)",
        )

        # 4) Sysprep & shutdown via EC2Launch v2
        sysprep_ps = r"""
$ErrorActionPreference='Stop'
Write-Host 'Starting Sysprep via EC2Launch...'
if (Get-Command Invoke-EC2Launch -ErrorAction SilentlyContinue) {
    Invoke-EC2Launch -Sysprep
} elseif (Test-Path 'C:\Program Files\Amazon\EC2Launch\EC2Launch.exe') {
    & 'C:\Program Files\Amazon\EC2Launch\EC2Launch.exe' sysprep
} else {
    Write-Error 'EC2Launch v2 not found.'
    exit 1
}
"""
        try:
            ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunPowerShellScript",
                Parameters={"commands": [sysprep_ps]},
                TimeoutSeconds=1800,
                Comment="Sysprep with EC2Launch v2",
            )
        except ClientError as e:
            log(f"Sysprep send_command returned: {e.response['Error']['Code']}")

        log("Waiting for instance to stop after Sysprep...")
        ec2.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])
        log("Instance is stopped. Creating AMI...")

        # 5) Create AMI
        img = ec2.create_image(
            InstanceId=instance_id,
            Name=args.ami_name,
            Description=f"Jenkins Windows worker baked {datetime.utcnow().isoformat()}Z",
            NoReboot=True,
        )
        ami_id = img["ImageId"]
        log(f"AMI creation started: {ami_id}")

        # Tag AMI
        tags = [
            {"Key": "Name", "Value": args.ami_name},
            {"Key": "BakedBy", "Value": "ami-jenkins-build-windows"},
        ] + [{"Key": k, "Value": str(v)} for k, v in extra_tags.items()]
        ec2.create_tags(Resources=[ami_id], Tags=tags)

        # Optional: wait until available
        log("Waiting for AMI to become available (this can take a while)...")
        ec2.get_waiter("image_available").wait(ImageIds=[ami_id])
        log(f"AMI is available: {ami_id}")

    finally:
        # 6) Terminate builder
        log("Terminating builder instance...")
        try:
            ec2.terminate_instances(InstanceIds=[instance_id])
        except Exception as e:
            log(f"Terminate failed: {e}")
        log("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
