# ami-jenkins-build-windows

python create_windows_ami.py \
 --base_ami ami-02e3d076cbd5c28fa \
 --ami_name my-windows-jenkins-worker \
 --region us-east-1 \
 --subnet_id subnet-12345678 \
 --security_group sg-12345678 \
 --volume_size 50 \
 --script_path ./init.ps1
