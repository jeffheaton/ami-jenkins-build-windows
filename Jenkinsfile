pipeline {
    agent any
    options { timestamps() }

    parameters {
        string(name: 'BASE_AMI',           defaultValue: 'ami-xxxxxxxx', description: 'Base Windows AMI')
        string(name: 'AMI_NAME',           defaultValue: 'jenkins-win-worker', description: 'New AMI name')
        string(name: 'REGION',             defaultValue: 'us-east-1', description: 'AWS region')
        string(name: 'SUBNET_ID',          defaultValue: 'subnet-xxxxxxxx', description: 'Subnet for builder')
        string(name: 'SECURITY_GROUP_ID',  defaultValue: 'sg-xxxxxxxx', description: 'SG with egress to SSM')
        string(name: 'INSTANCE_PROFILE',   defaultValue: 'SSMInstanceProfile', description: 'IAM instance profile name')
        string(name: 'VOLUME_SIZE',        defaultValue: '80', description: 'Root volume size (GiB)')
    }

    environment {
        AWS_DEFAULT_REGION = "${params.REGION}"
        PYTHONUNBUFFERED   = '1'
    }

    stages {
        stage('Bootstrap Python') {
            steps {
                sh '''
          python3 -m pip install --upgrade pip
          python3 -m pip install --upgrade boto3
        '''
            }
        }

        stage('Bake Windows AMI') {
            steps {
                sh """
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
