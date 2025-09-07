# ami-jenkins-build-windows

**Automated Windows AMI baking for Jenkins workers — no SSH/WinRM required.**  
This repo launches a temporary Windows EC2 “builder,” runs your `init.ps1` **inline via AWS Systems Manager (SSM)**, generalizes the instance with **EC2Launch v2 Sysprep**, creates an AMI, and terminates the builder.

## Why this approach?

Windows AMIs come with the SSM Agent. By giving the instance an SSM-enabled role and outbound HTTPS, we can push PowerShell with **Run Command**—no inbound ports, bastions, SSH, or WinRM headaches.

---

## Quick Start

1. **Prereqs**

- Python 3.9+ and AWS CLI v2 configured.
- `pip install boto3`
- An **instance profile** with the managed policy **`AmazonSSMManagedInstanceCore`** (attached to the builder instance).
- A **security group** that allows **outbound** HTTPS (TCP 443). No inbound rules required.
- A recent **Windows Server** base AMI (2019/2022) in your region.

2. **Repo files you edit**

- `init.ps1` — all the software you want baked into the AMI (choco tools, JDK, Git, Python, build tools, etc.).  
  _Keep Sysprep out of here; the driver invokes it for you._
- `create_ami_win.py` — the Python driver (SSM-based).

3. **Run it**

```bash
python create_ami_win.py \
  --base_ami ami-xxxxxxxxxxxxxxxxx \
  --ami_name jenkins-win-worker-2025-09-07 \
  --region us-east-1 \
  --subnet_id subnet-12345678 \
  --security_group sg-12345678 \
  --volume_size 80 \
  --script_path ./init.ps1 \
  --iam_instance_profile_name SSMInstanceProfile
```
