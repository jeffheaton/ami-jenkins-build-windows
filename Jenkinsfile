pipeline {
    agent { label 'linux-py-docker' }

    environment {
        SESSION_NAME = 'ami-general-session'
        REGION       = 'us-east-1'
        BASE_AMI     = 'ami-001adaa5c3ee02e10'   // Windows base AMI
        AMI_NAME     = "jenkins-win-py-${env.BUILD_NUMBER}"
    }

    stages {
        stage('Setup Environment') {
            steps {
                sh '''
                  set -euxo pipefail
                  # Ensure boto3 available for the driver
                  sudo pip3.12 install --upgrade pip boto3
                '''
            }
        }

        stage('Assume AWS Role') {
            steps {
                withCredentials([
                    string(credentialsId: 'jenkins-role-build-ami-linux-general', variable: 'ROLE_ARN') // your existing secret
                ]) {
                    script {
                        def assumeRoleOutput = sh(
                            script: """
                              aws sts assume-role \
                                --role-arn "$ROLE_ARN" \
                                --role-session-name "$SESSION_NAME" \
                                --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
                                --output text
                            """,
                            returnStdout: true
                        ).trim()
                        if (!assumeRoleOutput) { error "Failed to assume role: $ROLE_ARN" }
                        def creds = assumeRoleOutput.split()
                        env.AWS_ACCESS_KEY_ID     = creds[0]
                        env.AWS_SECRET_ACCESS_KEY = creds[1]
                        env.AWS_SESSION_TOKEN     = creds[2]
                    }
                }
            }
        }

        stage('Run Python Script') {
            steps {
                // No SSH key needed anymore (SSM). Keep your existing subnet/sg secrets.
                withCredentials([
                    string(credentialsId: 'private-subnet-id',          variable: 'SUBNET_ID'),
                    string(credentialsId: 'ssh-security-group-id',      variable: 'SECURITY_GROUP_ID'),
                    // New: instance profile name for the *builder* instance (create once in IAM)
                    string(credentialsId: 'windows-ssm-instance-profile', variable: 'INSTANCE_PROFILE')
                ]) {
                    sh """
                      set -euxo pipefail
                      python3.12 -u ./create_ami_win.py \
                        --base_ami "${BASE_AMI}" \
                        --ami_name "${AMI_NAME}" \
                        --region "${REGION}" \
                        --subnet_id "${SUBNET_ID}" \
                        --security_group "${SECURITY_GROUP_ID}" \
                        --volume_size "80" \
                        --script_path "./init.ps1" \
                        --iam_instance_profile_name "${INSTANCE_PROFILE}"
                    """
                }
            }
        }
    }
}
