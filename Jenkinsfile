pipeline {
    agent { label 'aws-ec2-linux' }   // or whatever your Linux label is
    options { timestamps() }

    parameters {
        string(name: 'BASE_AMI',          defaultValue: 'ami-xxxxxxxx',  description: 'Base Windows AMI')
        string(name: 'AMI_NAME',          defaultValue: 'jenkins-win-worker', description: 'New AMI name')
        string(name: 'REGION',            defaultValue: 'us-east-1',     description: 'AWS region')
        string(name: 'SUBNET_ID',         defaultValue: 'subnet-xxxxxxxx', description: 'Subnet for builder')
        string(name: 'SECURITY_GROUP_ID', defaultValue: 'sg-xxxxxxxx',   description: 'SG with egress to SSM')
        string(name: 'INSTANCE_PROFILE',  defaultValue: 'SSMInstanceProfile', description: 'IAM instance profile name')
        string(name: 'VOLUME_SIZE',       defaultValue: '80',            description: 'Root volume size (GiB)')
    }

    environment {
        AWS_DEFAULT_REGION = "${params.REGION}"
        PYTHONUNBUFFERED   = '1'
    }

    stages {
        stage('Bootstrap Python') {
            steps {
                sh '''
          set -euxo pipefail

          if ! python3 -m pip -V >/dev/null 2>&1; then
            if command -v dnf >/dev/null 2>&1; then
              sudo dnf -y install python3-pip
            elif command -v yum >/dev/null 2>&1; then
              sudo yum -y install python3-pip
            elif command -v apt-get >/dev/null 2>&1; then
              sudo apt-get update -y
              sudo apt-get install -y python3-pip
            else
              curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py
              python3 get-pip.py --user
            fi
          fi

          python3 -m pip install --upgrade pip
          if [ -f requirements.txt ]; then
            python3 -m pip install -r requirements.txt
          else
            python3 -m pip install boto3
          fi

          # quick sanity
          python3 - <<'PY'
import boto3, botocore, sys
print("boto3 ok:", boto3.__version__)
PY

          # optional: show identity if awscli exists
          if command -v aws >/dev/null 2>&1; then aws sts get-caller-identity || true; fi
        '''
            }
        }

        stage('Bake Windows AMI') {
            steps {
                sh """
          set -euxo pipefail
          python3 create_ami_win.py \
            --base_ami ${params.BASE_AMI} \
            --ami_name ${params.AMI_NAME} \
            --region ${params.REGION} \
            --subnet_id ${params.SUBNET_ID} \
            --security_group ${params.SECURITY_GROUP_ID} \
            --volume_size ${params.VOLUME_SIZE} \
            --script_path ./init.ps1 \
            --iam_instance_profile_name ${params.INSTANCE_PROFILE}
        """
            }
        }
    }
}
