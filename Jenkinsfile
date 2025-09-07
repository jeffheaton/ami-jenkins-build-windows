pipeline {
    agent { label 'linux-py-docker' }

    environment {
        SESSION_NAME     = 'ami-general-session'
        REGION           = 'us-east-1'
        BASE_AMI         = 'ami-001adaa5c3ee02e10'  // Windows base AMI
        INSTANCE_PROFILE = 'SSMInstanceProfile'     // <-- no Jenkins credential needed
    }

    stages {
        stage('Setup Environment') {
            steps {
                sh '''
                  set -euxo pipefail
                  sudo pip3.12 install --upgrade pip boto3
                '''
            }
        }

        stage('Assume AWS Role') {
            steps {
                withCredentials([
                    string(credentialsId: 'jenkins-role-build-ami-linux-general', variable: 'ROLE_ARN')
                ]) {
                    script {
                        // use triple-single-quoted Groovy string to avoid secret interpolation warning
                        def assumeRoleOutput = sh(
                            script: '''aws sts assume-role \
                              --role-arn "$ROLE_ARN" \
                              --role-session-name "$SESSION_NAME" \
                              --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
                              --output text''',
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
                withCredentials([
                    string(credentialsId: 'private-subnet-id',     variable: 'SUBNET_ID'),
                    string(credentialsId: 'ssh-security-group-id', variable: 'SECURITY_GROUP_ID')
                ]) {
                    sh """
                      set -euxo pipefail
                      python3.12 -u ./create_ami_win.py \
                        --base_ami "${BASE_AMI}" \
                        --ami_name "jenkins-win-py-${BUILD_NUMBER}" \
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
