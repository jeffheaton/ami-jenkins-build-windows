import boto3
import time
import argparse
import sys


def wait_for_ssm(
    instance_id: str, ssm_client, retries: int = 30, delay: int = 10
) -> None:
    """
    Polls until the SSM agent on the instance shows up in DescribeInstanceInformation.
    """
    print(f"Waiting for SSM agent on {instance_id}…")
    for attempt in range(1, retries + 1):
        resp = ssm_client.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
        )
        if resp.get("InstanceInformationList"):
            print("✔ SSM agent is online.")
            return
        print(f"  attempt {attempt}/{retries}…")
        time.sleep(delay)
    raise TimeoutError(f"SSM agent never came up after {retries * delay}s")


def run_ps_script(instance_id: str, ssm_client, script_path: str) -> None:
    """
    Sends a local PowerShell script to the instance via AWS-RunPowerShellScript,
    then polls until completion.
    """
    with open(script_path, "r", encoding="utf-8") as f:
        commands = f.read().splitlines()

    print(f"Sending PowerShell script ({script_path}) to {instance_id}…")
    resp = ssm_client.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunPowerShellScript",
        Parameters={"commands": commands},
        TimeoutSeconds=3600,
    )
    cmd_id = resp["Command"]["CommandId"]

    print("Polling for script result…")
    while True:
        inv = ssm_client.get_command_invocation(
            CommandId=cmd_id, InstanceId=instance_id
        )
        status = inv["Status"]
        if status in ("Success", "Failed", "Cancelled", "TimedOut"):
            print(f"→ SSM command finished with status: {status}")
            if status != "Success":
                err = inv.get("StandardErrorContent", "<no stderr>")
                raise RuntimeError(f"Script failed: {err.strip()}")
            return
        time.sleep(15)


def create_windows_ami(
    base_ami: str,
    ami_name: str,
    region: str,
    subnet_id: str,
    security_group: str,
    volume_size: int,
    script_path: str,
) -> None:
    ec2 = boto3.resource("ec2", region_name=region)
    ec2_client = boto3.client("ec2", region_name=region)
    ssm = boto3.client("ssm", region_name=region)

    instance = None
    try:
        print("Launching Windows EC2 instance…")
        instance = ec2.create_instances(
            ImageId=base_ami,
            IamInstanceProfile={"Name": "jenkins-role-build-ami-linux-general"},
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.medium",
            NetworkInterfaces=[
                {
                    "SubnetId": subnet_id,
                    "DeviceIndex": 0,
                    "AssociatePublicIpAddress": False,
                    "Groups": [security_group],
                }
            ],
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": volume_size,
                        "DeleteOnTermination": True,
                        "VolumeType": "gp3",
                    },
                }
            ],
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [{"Key": "Name", "Value": f"Temp-Windows-AMI-{ami_name}"}],
                }
            ],
            # Make sure this instance has an IAM role/profile with SSM permissions
        )[0]

        print("→ waiting for running…")
        instance.wait_until_running()
        instance.load()

        print("→ waiting for status OK…")
        waiter = ec2_client.get_waiter("instance_status_ok")
        waiter.wait(InstanceIds=[instance.id])

        # 1) Wait for SSM agent
        wait_for_ssm(instance.id, ssm)

        # 2) Run your init.ps1 via SSM
        run_ps_script(instance.id, ssm, script_path)

        # 3) Stop, snapshot, and bake AMI
        print("Stopping instance…")
        instance.stop()
        instance.wait_until_stopped()

        print(f"Creating AMI '{ami_name}'…")
        resp = ec2_client.create_image(
            InstanceId=instance.id,
            Name=ami_name,
            # On Windows you might omit NoReboot for a clean shutdown
            NoReboot=True,
        )
        ami_id = resp["ImageId"]

        print(f"→ waiting for AMI {ami_id} to become available…")
        image_waiter = ec2_client.get_waiter("image_available")
        image_waiter.wait(ImageIds=[ami_id])
        print(f"✔ Windows AMI created: {ami_id}")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
    finally:
        if instance:
            instance.reload()
            if instance.state["Name"] not in ("terminated",):
                print("Terminating temp instance…")
                instance.terminate()
                instance.wait_until_terminated()
                print("✔ Instance terminated.")


if __name__ == "__main__":
    p = argparse.ArgumentParser("Create a Windows AMI via SSM")
    p.add_argument("--base_ami", required=True, help="Windows base AMI ID")
    p.add_argument("--ami_name", required=True, help="Name for the new AMI")
    p.add_argument("--region", required=True, help="AWS region")
    p.add_argument("--subnet_id", required=True, help="Subnet ID")
    p.add_argument("--security_group", required=True, help="Security Group ID")
    p.add_argument(
        "--volume_size",
        type=int,
        default=30,
        help="Root EBS volume size (GB)",
    )
    p.add_argument(
        "--script_path",
        required=True,
        help="Path to your init.ps1 PowerShell setup script",
    )

    args = p.parse_args()
    create_windows_ami(
        args.base_ami,
        args.ami_name,
        args.region,
        args.subnet_id,
        args.security_group,
        args.volume_size,
        args.script_path,
    )
